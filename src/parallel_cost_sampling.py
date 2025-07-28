import cost_calculations as cc
import process_RME_data as prd
import math
import pandas as pd
import numpy as np

config = cc.load_config()

def para_sample_econ(rme_files_path, nsims, ncores=5, uncertainty_dict=prd.default_uncertainty_dict(),
                                metrics = [prd.rci, prd.raw_rti, prd.rfi],
                                max_dist = 25.0,
                                economics_spatial_filepath='.//datasets//econ_spatial.csv',
                                econ_storage_path=".//econ_outputs//"
                                ):
    """
    Run economics metrics data creation files so that corresponding cost data can be sampled in parallel.
    Saves ID key files so that these are available for all cores while sampling cost models in parallel.
    Also saves scenario references so that parallel samples process the correct scenario sims.

    Parameters
    ----------
        rme_files_path : string
            String giving the path to resultset folder.
        nsims : int
            Number of simulations to sampling (including uncertainty types as specified)
        ncores : int
            Number of cores to sample cost models over.
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
        """

    nbatches = math.ceil(nsims/ncores)

    # Create metric datafiles for economics modelling and extract filename for intervention key
    int_keys_fn = prd.create_economics_metric_files(rme_files_path, nsims, nbatches, ncores=ncores,
                                                    metrics=metrics, max_dist=max_dist,
                                                    uncertainty_dict=uncertainty_dict,
                                                    economics_spatial_filepath=economics_spatial_filepath,
                                                    econ_storage_path=econ_storage_path)

    return int_keys_fn, nbatches

def calc_costs_para(iter_id, int_keys_fn, n_sims, deploy_model_filepath=config["deploy_model_filepath"],
                                prod_model_filepath=config["prod_model_filepath"],
                                cont_p = 0.25):
    """
    Wrapper function to allow cost model sampling in parallel over ncores.

    Parameters
    ----------
        ID_key : dataframe
            Dataframe created by running create_economics_metric_files connecting economics metric files to
            intervention scenario IDs and parameters.
        nsims : int
            Total number of draws to sample cost models, should match ecological metrics sampling.
        deploy_model_filepath : string
            Path to deployment cost model.
        prod_model_filepath : string
            Path to production cost model.
        cont_p : float
            Contingency cost proportion.
    """
    return cc.calculate_costs(int_keys_fn, n_sims, iter_id=iter_id, deploy_model_filepath=deploy_model_filepath,
                                prod_model_filepath=prod_model_filepath,
                                cont_p=cont_p)

def post_process_costs(result, nbatches, nsims):
    """
    Save cost samples run in parallel in a single file which is in the correct format for the economics modelling.

    Parameters
    ----------
        result : list
            List of filenames for saved parallel cost data runs.
        nbatches : int
            Number of draws run on each core.
        nsims : int
            Total number of draws to sample cost models, should match ecological metrics sampling.
    """
    for iv_id in range(len(result[0])):
        init_cost_df = pd.read_csv(result[0][iv_id])
        sim_cols = ["year", "component"] + ["draw"+str(i) for i in range(1, nsims+1)]

        cost_df = pd.DataFrame(np.zeros((init_cost_df.shape[0],2+nsims)), columns = sim_cols)
        cost_df.loc[:,["year", "component"]] = init_cost_df[["year", "component"]]

        save_fn = result[0][iv_id].split("id")[0][:-6]+".csv"

        for (idx_r, res) in enumerate(result):
            cost_temp = pd.read_csv(res[iv_id])
            cost_df.iloc[:, idx_r*nbatches+2:idx_r*nbatches+2+nbatches] = cost_temp.iloc[:, 2:nbatches+2]

        cost_df.to_csv(save_fn, index=False)
