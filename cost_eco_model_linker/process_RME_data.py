import os
from os.path import join as path_join

from itertools import batched

import netCDF4 as nc
import pandas as pd
import geopandas as gp
import numpy as np
import json

from .calculate_metrics import (
    extract_metrics,
    default_uncertainty_dict,
    indicator_params,
)
from .reef_distances import find_max_reef_distance

THIS_DIR = os.path.dirname(__file__)


def load_reef_data():
    """
    Loads key reef spatial data.
    """
    return gp.read_file(path_join(THIS_DIR, "datasets", "reefmod_gbr.gpkg"))


def load_regions_data(economics_spatial_filepath: str):
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
    regions_data = pd.read_csv(economics_spatial_filepath)  # Economic spatial data key

    return regions_data


def load_result_files(rme_files_path: str):
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

    # intervention scenarios table
    scens_df = pd.read_csv(path_join(rme_files_path, "iv_yearly_scenarios.csv"))
    results_data = nc.Dataset(path_join(rme_files_path, "results.nc"))  # Metric results

    # Load struct with interventions data
    with open(path_join(rme_files_path, "scenario_info.json"), "r") as file:
        iv_dict = json.load(file)

    return results_data, scens_df, iv_dict


def create_base_economics_dataframe(
    regions_data: pd.DataFrame, reef_spatial_data: pd.DataFrame, years: list
):
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
    regions_data = regions_data.sort_values(by="Reef_ID", ignore_index=True).copy()

    # Add UNIQUE_ID cross-reference for estimating reef distance to port
    regions_data["UNIQUE_ID"] = reef_spatial_data["UNIQUE_ID"].values

    # Create year dataframe
    years_df = pd.DataFrame(
        {
            "year_absolute": years,
            "year_relative": 0,  # Placeholder if needed later
        }
    )

    # Cross join: each reef with each year
    data_store = regions_data.merge(years_df, how="cross")

    return data_store, regions_data


def area_weighted_rti(metrics_dict: dict, metrics_df: pd.DataFrame):
    """
    Processes metrics dict into continuous reef condition weighted by reef area.

    Parameters
    ----------
    metrics_dict : dict
        Dict containing key sampled metrics and the RCI
    metrics_df : dataframe
        Dataframe containing scenario summary dataframe
    """
    return np.transpose(
        metrics_dict["RTI"]
        * np.array(
            metrics_df["total_area_nine_zones"]
            / np.sum(metrics_df["total_area_nine_zones"])
        ),
        (1, 0),
    )


def rci(metrics_dict: dict, metrics_df: pd.DataFrame, rci_threshold=0.6):
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
    rci[rci < rci_threshold] = 0

    return np.transpose(rci * np.array(metrics_df["total_area_nine_zones"]), (1, 0))


def coral_area_saved(metrics_dict: dict, metrics_df: pd.DataFrame):
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
    return np.transpose(
        metrics_dict["total_cover"]
        * np.array(metrics_df["total_area_nine_zones"] / 100),
        (1, 0),
    )


def rfi(metrics_dict: dict, metrics_df: pd.DataFrame, rfi_thresholds=[0.74, 29.91]):
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
    rfi[rfi > rfi_thresholds[1]] = rfi_thresholds[1]

    return np.transpose(rfi, (1, 0))


def raw_reefcond(metrics_dict: dict, metrics_df: pd.DataFrame):
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


def raw_rti(metrics_dict: dict, metrics_df: pd.DataFrame):
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


def coral_cover(metrics_dict: dict, metrics_df: pd.DataFrame):
    """
    Processes metrics dict coral cover for table storage.

    Parameters
    ----------
    metrics_dict : dict
        Array containing key sampled metrics and the RTI
    metrics_df : dataframe
        Dataframe containing scenario summary dataframe
    """
    return np.transpose(metrics_dict["total_cover"], (1, 0))


def shelter_volume(metrics_dict: dict, metrics_df: pd.DataFrame):
    """
    Processes metrics dict into shelter volume for table storage.

    Parameters
    ----------
    metrics_dict : dict
        Array containing key sampled metrics and the RTI
    metrics_df : dataframe
        Dataframe containing scenario summary dataframe
    """
    return np.transpose(metrics_dict["shelter_volume"], (1, 0))


def coraljuv_relative(metrics_dict: dict, metrics_df: pd.DataFrame):
    """
    Processes metrics dict into relative juvenile coral cover for table storage.

    Parameters
    ----------
    metrics_dict : dict
        Array containing key sampled metrics and the RTI
    metrics_df : dataframe
        Dataframe containing scenario summary dataframe
    """
    return np.transpose(metrics_dict["coraljuv_relative"], (1, 0))


def COTSrel_complementary(metrics_dict: dict, metrics_df: pd.DataFrame):
    """
    Processes metrics dict into relative COTS complementary cover for table storage.

    Parameters
    ----------
    metrics_dict : dict
        Array containing key sampled metrics and the RTI
    metrics_df : dataframe
        Dataframe containing scenario summary dataframe
    """
    return np.transpose(metrics_dict["COTSrel_complementary"], (1, 0))


def rubble_complementary(metrics_dict: dict, metrics_df: pd.DataFrame):
    """
    Processes metrics dict into rubble complementary cover for table storage.

    Parameters
    ----------
    metrics_dict : dict
        Array containing key sampled metrics and the RTI
    metrics_df : dataframe
        Dataframe containing scenario summary dataframe
    """
    return np.transpose(metrics_dict["rubble_complementary"], (1, 0))


def create_economics_metric_files(
    rme_files_path: str,
    nsims: int,
    stores,
    nbatches=None,
    uncertainty_dict: dict = None,
    ncores: int = 1,
    metrics=None,
    max_dist=25.0,
    economics_spatial_filepath=None,
) -> tuple[str, list[str]]:
    """
    Main function for creating metric file summaries for input to economics modelling.

    Parameters
    ----------
    rme_files_path : str
        Path to resultset folder.
    nsims : int
        Number of simulations to sample (including uncertainty types as specified).
    stores : object
        Storage paths object with econ_dir and intervention_keys_dir attributes.
    nbatches : int, optional
        Number of batches. If None, defaults to nsims (single batch).
    uncertainty_dict : dict, optional
        Information on uncertainty types to sample.
    ncores : int, default=1
        Number of cores for output file generation.
    metrics : list, optional
        List of metric functions to calculate. Defaults to [rci, raw_rti, rfi].
    max_dist : float, default=25.0
        Maximum distance (NM) between reefs within a cluster for distance calculations.
    economics_spatial_filepath : str, optional
        Path to economics spatial data (econ_spatial.csv).

    Returns
    -------
    run_id : str
        Base filename identifier for this run.
    metric_filepaths : list
        List of generated metric file paths for each intervention.
    """
    # Set defaults
    if economics_spatial_filepath is None:
        economics_spatial_filepath = path_join(THIS_DIR, "datasets", "econ_spatial.csv")
    if uncertainty_dict is None:
        uncertainty_dict = default_uncertainty_dict()
    if metrics is None:
        metrics = [rci, raw_rti, rfi]

    nbatches = nsims if nbatches is None else nbatches

    # Load all required data
    regions_data = load_regions_data(economics_spatial_filepath)
    results_data, scens_df, iv_dict = load_result_files(rme_files_path)
    reef_spatial_data = load_reef_data()

    # Extract time information
    years = results_data["timesteps"][:]
    start_year, end_year = years[0], years[-1]

    # Get unique intervention IDs
    intervention_ids = np.unique(scens_df["intervention id"])

    # Separate intervention and counterfactual scenario indices
    is_counterfactual = np.array(iv_dict["counterfactual"], dtype=bool)
    unique_iv_scens = np.where(~is_counterfactual)[0]
    unique_cf_scens = np.where(is_counterfactual)[0]

    # Create base dataframe structure (without sim columns yet)
    base_data_store, regions_data = create_base_economics_dataframe(
        regions_data, reef_spatial_data, years
    )

    # Setup storage for ecological sample IDs
    store_ecol_ids = np.zeros((nsims, len(intervention_ids)), dtype=int)

    # Generate batch indices
    if nsims != nbatches:
        nmembers = int(np.ceil(nsims / nbatches))
        batch_chunks = list(batched(range(nsims), nmembers))
    else:
        batch_chunks = [
            list(range(nsims)),
        ]

    # Setup filenames for outputs
    ecol_uncert = uncertainty_dict["ecol_uncert"]
    expert_uncert = uncertainty_dict["expert_uncert"]
    base_met_filename = f"_uncertainty_ecol{ecol_uncert}_indicator{expert_uncert}_var_"

    run_id = os.path.basename(rme_files_path) + "_run"
    id_filename = path_join(
        stores.intervention_keys_dir, f"intervention_ID_key_{run_id}"
    )
    ecol_id_filename = path_join(
        stores.intervention_keys_dir, f"intervention_rep_idx_{run_id}"
    )

    # Storage for results
    metric_filepaths = []
    id_key_dfs = []

    # Process each intervention
    for iv_idx, iv_id in enumerate(intervention_ids):
        # Filter scenarios for this intervention
        scens_df_iv = scens_df[scens_df["intervention id"] == iv_id].copy()
        n_reps = scens_df_iv["rep"].max()

        # Get intervention reefs
        reefset_names = scens_df_iv["reefset"].unique()
        iv_reefs = sum([iv_dict[reefset_name] for reefset_name in reefset_names], [])

        # Calculate relative year (0 on first intervention year)
        intervention_start = scens_df_iv["year"].min()
        intervention_start_idx = np.where(years == intervention_start)[0][0]
        data_store = base_data_store.copy()
        data_store["year_relative"] = data_store["year_absolute"] - intervention_start

        # Get scenario indices for this intervention and its counterfactual
        scen_id_start = iv_idx * n_reps
        scen_id_end = scen_id_start + n_reps
        iv_scens = unique_iv_scens[scen_id_start:scen_id_end]
        cf_scens = unique_cf_scens[scen_id_start:scen_id_end]

        # Create intervention key dataframe
        scen_cols = ["intervention id", "year", "rep", "number of corals"]
        id_key_df = scens_df_iv[scen_cols].assign(
            distance_to_port_NM=0.0,
            furthest_representative_reef="",
            closest_representative_reef="",
        )

        # Calculate and store distance to port
        rep_reefs_sort, rep_reef_names, total_dist = find_max_reef_distance(
            reef_spatial_data, regions_data, iv_reefs, max_dist=max_dist
        )
        id_key_df["furthest_representative_reef"] = rep_reef_names[-1]
        id_key_df["closest_representative_reef"] = rep_reef_names[0]
        id_key_df["distance_to_port_NM"] = total_dist

        # Process batches
        batch_files = []

        # Shared template for all simulations
        data_store.to_parquet(
            path_join(stores.econ_dir, "sim_template.parq"), index=False
        )

        for batch_idx, batch_sel in enumerate(batch_chunks):
            ds = pd.DataFrame()

            # Extract metrics for intervention and counterfactual
            (
                maxcoraljuv,
                sheltervolume_parameters,
                rci_crit,
                rti_intercept,
                rti_cov_slope,
                rti_shelt_slope,
                rti_juv_slope,
                rti_cots_slope,
                rti_rubble_slope,
                intercept1,
                intercept2,
                slope1,
                slope2,
            ) = indicator_params(
                results_data,
                iv_scens,
                uncertainty_dict=uncertainty_dict,
                juv_max_years=[0, int(intervention_start_idx - 1)],
            )

            indicator_params_dict = {
                "maxcoraljuv": maxcoraljuv,
                "sheltervolume_parameters": sheltervolume_parameters,
                "rci_crit": rci_crit,
                "rti_intercept": rti_intercept,
                "rti_cov_slope": rti_cov_slope,
                "rti_shelt_slope": rti_shelt_slope,
                "rti_juv_slope": rti_juv_slope,
                "rti_cots_slope": rti_cots_slope,
                "rti_rubble_slope": rti_rubble_slope,
                "intercept1": intercept1,
                "intercept2": intercept2,
                "slope1": slope1,
                "slope2": slope2,
            }

            metrics_data_iv, ecol_ids = extract_metrics(
                results_data,
                iv_scens,
                len(batch_sel),
                uncertainty_dict=uncertainty_dict,
                curr_eco_sim_idx=None,
                indicator_param_dict=indicator_params_dict,
            )

            metrics_data_cf, _ = extract_metrics(
                results_data,
                cf_scens,
                len(batch_sel),
                uncertainty_dict=uncertainty_dict,
                curr_eco_sim_idx=ecol_ids
                - n_reps,  # Use same ecological sample for counterfactual as for intervention, adjusting for scenario index shift
                indicator_param_dict=indicator_params_dict,  # Use same indicator params for counterfactual as for intervention
            )

            # Adjust ecological IDs to ignore counterfactuals in cost sampling
            max_rep = id_key_df["rep"].max()
            ecol_ids[ecol_ids >= max_rep] -= max_rep
            store_ecol_ids[batch_sel, iv_idx] = ecol_ids

            # Prepare simulation columns for this batch
            sim_cols = [f"sim_{b + 1}" for b in batch_sel]

            # Calculate and save metrics for each metric function
            for met_func in metrics:
                fn_suffix = f"{base_met_filename}{met_func.__name__}_batch{batch_idx}"

                # Intervention results
                iv_results = met_func(metrics_data_iv, data_store)
                iv_filename = f"ID{iv_id}_intervention{fn_suffix}.parq"
                ds[sim_cols] = iv_results

                ds.to_parquet(
                    path_join(stores.econ_dir, iv_filename),
                    index=False,
                    compression=None,
                )
                batch_files.append(iv_filename)

                # Counterfactual results (reuse the same dataframe)
                cf_results = met_func(metrics_data_cf, data_store)
                cf_filename = f"ID{iv_id}_counterfactual{fn_suffix}.parq"
                ds[sim_cols] = cf_results

                ds.to_parquet(
                    path_join(stores.econ_dir, cf_filename),
                    index=False,
                    compression=None,
                )
                batch_files.append(cf_filename)

        # Finalize intervention key with metadata
        id_key_df = id_key_df.assign(
            results_filename=f"ID{iv_id}_{base_met_filename}",
            number_of_species=6,
            start_year=start_year,
            end_year=end_year,
            climate_model=scens_df_iv["GCM name"].values,
        ).rename(
            columns={
                "number of corals": "number_of_1YO_corals",
                "intervention id": "ID",
                "year": "intervention_years",
            }
        )

        id_key_dfs.append(id_key_df)
        metric_filepaths.append(batch_files)

    # Combine all intervention keys
    id_key_df_all = pd.concat(id_key_dfs, ignore_index=True)

    # Save intervention key and ecological ID files (one per core)
    for core_idx in range(ncores):
        id_key_df_all.to_csv(f"{id_filename}{core_idx}.csv", index=False)

        pd.DataFrame(
            store_ecol_ids[nbatches * core_idx : nbatches * (core_idx + 1), :] + 1,
            columns=[str(id_val) for id_val in intervention_ids],
        ).to_csv(f"{ecol_id_filename}{core_idx}.csv", index=False)

    return os.path.basename(rme_files_path), metric_filepaths
