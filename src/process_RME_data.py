import netCDF4 as nc
import pandas as pd
import geopandas as gp
import numpy as np
import json

from calculate_metrics import extract_metrics, default_uncertainty_dict
from reef_distances import find_max_reef_distance

def load_reef_data():
    """
    Loads key reef spatial data.
    """
    return gp.read_file(".\\datasets\\reefmod_gbr.gpkg")

def load_regions_data(economics_spatial_filepath):
    """
    Loads key economics spatial data.

    Parameters
    ----------
        economics_spatial_filepath : string
            String giving the path to economics spatial data.

    Returns
    -------
        regions_data : dataframe
    """
    regions_data = pd.read_csv(economics_spatial_filepath) # Economic spatial data key

    return regions_data

def load_result_files(rme_files_path):
    """
    Loads results files generated from running scenarios in ReefModEngine.jl.

    Parameters
    ----------
        rme_files_path : string
            String giving the path to resultset folder.

    Returns
    -------
        results_data : dict
            Dict containing numpy arrays of results data from running ReefModEngine.jl.
        scens_df : dataframe
            Describes scenario parameters year-by-year, including rep, year and intervention levels.
        iv_dict : dict
            Contains other key scenario info, such as whether the scenario is counterfactual or intervention.
    """
    scens_df = pd.read_csv(rme_files_path+"\\iv_yearly_scenarios.csv") # intervention scenarios table
    results_data = nc.Dataset(rme_files_path+"\\results.nc") # Metric results

    # Load struct with interventions data
    with open(rme_files_path+'\\scenario_info.json', 'r') as file:
        iv_dict = json.load(file)

    return results_data, scens_df, iv_dict

def create_base_economics_dataframe(regions_data, reef_spatial_data, years):
    """
    Creates base structure for metrics summary files input to economics modelling.

    Parameters
    ----------
        regions_data : dataframe
            A dataframe with key spatial and economics data for each reef in the GBR (loaded from econ_spatial.csv).
        reef_spatial_data : dataframe
            A dataframe from the RME specified key reef IDs and spatial information (loaded from reefmod_gbr.gpkg).
        years : list
            Years to be included in the economics output file from the ecological modelling.

    Returns
    -------
        data_store: dataframe
            Basic economics file structure to save for each intervention/counterfactual scenario.
    """
    regions_data = regions_data.sort_values(by="Reef_ID", ignore_index=True)
    n_reefs = len(regions_data.reef_name)

    # Setup base dataframe structure
    # Reef_ID holds indices for corresponding ReefModEngine order of reefs
    data_store = pd.DataFrame(np.zeros((n_reefs*len(years), 2), dtype=int), columns=["year_absolute", "year_relative"])
    data_store.loc[:, "year_absolute"] = np.array(list(years)*n_reefs)
    data_store = pd.concat([data_store, pd.DataFrame(np.repeat(regions_data, len(years), axis=0), columns = regions_data.columns)], axis=1)

    # Add UNIQUE ID to regions data to allow cross-referencing for estimating reef distance to port
    regions_data.loc[:, "UNIQUE_ID"] = reef_spatial_data["UNIQUE_ID"]

    return data_store, regions_data

def area_weighted_rti(metrics_dict, metrics_df):
    """
    Processes metrics dict into continuous reef condition weighted by reef area.

    Parameters
    ----------
        metrics_dict : dict
            Dict containing key sampled metrics and the RCI
        metrics_df : dataframe
            Dataframe containing scenario summary dataframe
    """
    return np.transpose(metrics_dict["RTI"]*np.array(metrics_df["total_area_nine_zones"]/np.sum(metrics_df["total_area_nine_zones"])),(1, 0))

def rci(metrics_dict, metrics_df, rci_threshold=0.6):
    """
    Processes metrics dict into area at threshold RCI and above.

    Parameters
    ----------
        metrics_dict : dict
            Dict containing key sampled metrics and the RCI
        metrics_df : dataframe
            Dataframe containing scenario summary dataframe
        rci_threshold : float
            RCI threshold (in (0.0, 1.0)) above which to calculate area saved for.
    """
    rci = metrics_dict["RCI"]
    rci[rci >= rci_threshold] = 1
    rci[rci < rci_threshold]  = 0

    return np.transpose(rci*np.array(metrics_df["total_area_nine_zones"]),(1, 0))

def coral_area_saved(metrics_dict, metrics_df):
    """
    Processes metrics dict into total area of coral cover in hectares.

    Parameters
    ----------
        metrics_dict : dict
            Dict containing key sampled metrics and the RCI
        metrics_df : dataframe
            Dataframe containing scenario summary dataframe
    """
    # Convert to hectares by dividaing by 100
    return np.transpose(metrics_dict["total_cover"]*np.array(metrics_df["total_area_nine_zones"]/100),(1, 0))

def rfi(metrics_dict, metrics_df, rfi_thresholds=[0.74, 29.91]):
    """
    Processes metrics dict into area at threshold RFI and above.
    Minimum fish biomass is 0.74 kg km2. This was the minimum observation in the Graham and Nash,
    2012 dataset. Similarly, max fish biomass is 29.91kg km2.

    Parameters
    ----------
        metrics_dict : dict
            Dict containing key sampled metrics and the RFI
        metrics_df : dataframe
            Dataframe containing scenario summary dataframe
        rfi_thresholds : float
            RFI thresholds (min and max fish biomass)
    """
    rfi = metrics_dict["RFI"]
    rfi[rfi < rfi_thresholds[0]] = rfi_thresholds[0]
    rfi[rfi > rfi_thresholds[1]]  = rfi_thresholds[1]

    return np.transpose(rfi, (1, 0))

def raw_rci(metrics_dict, metrics_df):
    """
    Processes metrics dict into raw RCI for table storage.

    Parameters
    ----------
        metrics_dict : dict
            Array containing key sampled metrics and the RCI
        metrics_df : dataframe
            Dataframe containing scenario summary dataframe
    """
    return np.transpose(metrics_dict["RCI"], (1, 0))

def raw_rti(metrics_dict, metrics_df):
    """
    Processes metrics dict into raw RTI for table storage.

    Parameters
    ----------
        metrics_dict : dict
            Array containing key sampled metrics and the RTI
        metrics_df : dataframe
            Dataframe containing scenario summary dataframe
    """
    return np.transpose(metrics_dict["RTI"], (1, 0))

def create_economics_metric_files(rme_files_path, nsims, nbatches=None,
                                uncertainty_dict=default_uncertainty_dict(),
                                ncores=1,
                                metrics = [rci, raw_rti, rfi],
                                max_dist = 25.0,
                                economics_spatial_filepath='.//datasets//econ_spatial.csv',
                                econ_storage_path=".//econ_outputs//",
                                criteria_threshold=0.6,
                                cots_outbreak_threshold=1500.0):
    """
    Main function for creating metric file summarys for input to economics modelling.

    Parameters
    ----------
        rme_files_path : string
            String giving the path to resultset folder.
        nsims : int
            Number of simulations to sampling (including uncertainty types as specified)
        uncertainty_dict : dict
            Contains information on what uncertainty types to sample.
        max_dist : float
            Maximum distance between reefs within a "cluster". Total distance to port is calculated as distance
            to port for closest reef cluster + distance between each additional further cluster where distance between
            clusters is calculated as distance between the reefs furthest from port in each cluster.
        economics_spatial_filepath : string
            Filepath for economics spatial data (econ_spatial.csv)
        econ_storage_path : string
            Where to store output economics metrics files.

    Returns
    -------
        id_filename : string
            Filename for ID key file, which links economics metrics
    """
    # If nbatches not provided, set to nsims (calculate in one go rather than in sets of nbatches)
    nbatches = nbatches if nbatches is not None else nsims

    # Load all relevant data
    regions_data = load_regions_data(economics_spatial_filepath)

    # Scenario dataframe and metric results from RME runs
    results_data, scens_df, iv_dict = load_result_files(rme_files_path)

    # Load reef spatial data to cross check reef UNIQUE_ID with GBRMPA_ID
    reef_spatial_data = load_reef_data()

    # Create base dataframe for storing metric results for economics model
    years = results_data["timesteps"][:]
    start_year = years[0]
    end_year = years[-1]

    # Get unique intervention IDs from result set (a unique intervention scenario run in ReefModEngine.jl)
    intervention_ids = np.unique(scens_df["intervention id"])

    # Extract ids for cf and intervention runs
    unique_iv_scens = np.where(~np.array(iv_dict["counterfactual"]).astype(bool))[0]
    unique_cf_scens = np.where(np.array(iv_dict["counterfactual"]).astype(bool))[0]

    # Setup key storage for metrics datafiles and ecological sample ids
    data_store, regions_data = create_base_economics_dataframe(regions_data, reef_spatial_data, years)

    # Add columns to store sampled metrics
    sim_cols = ["sim_{0}".format(i) for i in range(1,nbatches+1)]
    store_sims = pd.DataFrame(np.zeros((data_store.shape[0], len(sim_cols))), columns = sim_cols)
    data_store = pd.concat((data_store, store_sims), axis=1)
    store_ecol_ids = np.zeros((nsims, len(intervention_ids)), dtype=int)

    # Setup key table structure used by economics modelling
    id_key_df_store = pd.DataFrame(columns=['ID', 'intervention_years', 'rep', 'number_of_1YO_corals',
       'distance_to_port_NM', 'furthest_representative_reef',
       'closest_representative_reef', 'results_filename',
       'number_of_species', 'start_year', 'end_year', 'climate_model'])

    # Base filename for saving metrics
    base_met_filename = '_uncertainty_ecol'+str(uncertainty_dict["ecol_uncert"])+'_indicator'+str(uncertainty_dict["expert_uncert"])+'_var_'
    # Save intervention key for generating cost data file for saved intervention and cf files
    id_filename = ".\\intervention_keys\\intervention_ID_key_"+rme_files_path.split("\\")[-1]+"_run"
    ecol_id_filename = ".\\intervention_keys\\intervention_rep_idx_"+rme_files_path.split("\\")[-1]+"_run"
    metric_filepaths = [""]*len(intervention_ids)

    # Save a csv for each unique intervention, one for cf and one for iv runs
    for (iv_idx, iv_id) in enumerate(intervention_ids):

        store_metric_filepaths = [""]*len(metrics)*ncores*2
        filecount = 0
        # Get scenario table for intervention
        scens_idx = scens_df["intervention id"]==iv_id
        scens_df_iv = scens_df[scens_idx]
        n_reps = max(scens_df_iv["rep"])

        reefset_names = np.unique(scens_df_iv["reefset"])
        iv_reefs = sum([iv_dict[reefset_name] for reefset_name in reefset_names], [])

        # Year relative starts at 0 on the first year of intervention
        data_store.loc[:, "year_relative"] = data_store["year_absolute"] - (min(scens_df_iv["year"]) + 1)

        # Scenario ids for CF and counterfactual
        iv_scens = unique_iv_scens[(iv_idx*n_reps):(iv_idx*n_reps)+n_reps]
        cf_scens = unique_cf_scens[(iv_idx*n_reps):(iv_idx*n_reps)+n_reps]

        # Setup structure for intervention key - links intervention ID and filename to cost model data
        id_key_df = scens_df_iv[["intervention id", "year", "rep", "number of corals"]]
        n_scens_id, id_key_n_col = id_key_df.shape

        id_key_df.insert(id_key_n_col, "distance_to_port_NM", np.zeros((n_scens_id,)))
        id_key_df.insert(id_key_n_col+1, "furthest_representative_reef", np.repeat("", (n_scens_id,)))
        id_key_df.insert(id_key_n_col+2, "closest_representative_reef",  np.repeat("", (n_scens_id,)))

        # Add distance to port data to save in intervention key
        [rep_reefs_sort, total_dist] = find_max_reef_distance(reef_spatial_data, regions_data, iv_reefs, max_dist = max_dist)

        # Store furthest and closest reefs in representative clsuters
        id_key_df.loc[:, "furthest_representative_reef"] = rep_reefs_sort[-1]
        id_key_df.loc[:, "closest_representative_reef"] = rep_reefs_sort[0]
        id_key_df.loc[:, "distance_to_port_NM"] = total_dist

        for i_core in range(ncores):
            # Extract metrics for intervention and counterfactual scenarios
            metrics_data_iv, ecol_ids = extract_metrics(results_data, iv_scens, nbatches, uncertainty_dict=uncertainty_dict,
                                                        criteria_threshold=criteria_threshold, cots_outbreak_threshold=cots_outbreak_threshold)
            metrics_data_cf, _ = extract_metrics(results_data, cf_scens, nbatches, uncertainty_dict=uncertainty_dict,
                                                 criteria_threshold=criteria_threshold, cots_outbreak_threshold=cots_outbreak_threshold)

            # Result sampling ids to ignore counterfactuals in cost sampling
            ecol_ids[ecol_ids>=max(id_key_df["rep"])] = ecol_ids[ecol_ids>=max(id_key_df["rep"])]-max(id_key_df["rep"])
            store_ecol_ids[nbatches*i_core:nbatches*(i_core+1), iv_idx] = ecol_ids

            for met_func in metrics:
                data_store[sim_cols] = met_func(metrics_data_iv, data_store)
                store_metric_filepaths[filecount] = 'ID'+str(iv_id)+'_intervention'+base_met_filename+met_func.__name__+'_batch'+str(i_core)+'.csv'
                data_store.to_csv(econ_storage_path+store_metric_filepaths[filecount], index=False)
                data_store[sim_cols] = met_func(metrics_data_cf, data_store)
                store_metric_filepaths[filecount+1] = 'ID'+str(iv_id)+'_counterfactual'+base_met_filename+met_func.__name__+'_batch'+str(i_core)+'.csv'
                data_store.to_csv(econ_storage_path+store_metric_filepaths[filecount+1], index=False)
                filecount+=2

        # Drop data columns to allow those for next intervention to be added
        data_store = data_store.drop(sim_cols, axis=1)

        # Add to record key data for cost modelling
        id_key_n_col = id_key_df.shape[1]

        id_key_df.insert(id_key_n_col, "results_filename", np.repeat('ID'+str(iv_id)+'_'+base_met_filename, (n_scens_id,)))
        id_key_df.insert(id_key_n_col+1,"number_of_species", np.ones((n_scens_id,))*6)
        id_key_df.insert(id_key_n_col+2, "start_year", np.repeat(start_year, (n_scens_id,)))
        id_key_df.insert(id_key_n_col+3, "end_year", np.repeat(end_year, (n_scens_id,)))
        id_key_df.insert(id_key_n_col+4, "climate_model", scens_df_iv["GCM name"].values)
        id_key_df = id_key_df.rename(columns={'number of corals':'number_of_1YO_corals','intervention id':'ID', 'year':'intervention_years'})

        if id_key_df_store.empty:
            id_key_df_store = id_key_df
        else:
            id_key_df_store = pd.concat([id_key_df_store, id_key_df])

        metric_filepaths[iv_idx] = store_metric_filepaths

    for i_core in range(ncores):
        id_key_df_store.to_csv(id_filename+str(i_core)+".csv")
        store_ecol_ids_df = pd.DataFrame(store_ecol_ids[nbatches*i_core:nbatches*(i_core+1), :], columns=[str(id) for id in intervention_ids])
        store_ecol_ids_df.to_csv(ecol_id_filename+str(i_core)+".csv")

    return rme_files_path.split("\\")[-1], metric_filepaths
