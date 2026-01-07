import os
from os.path import join as path_join

import math

from .setup_results import RESULT_DIRS, OutputStores
from . import process_RME_data as prd
from . import cost_calculations as cc
import pandas as pd
import numpy as np

THIS_DIR = os.path.dirname(__file__)


def para_sample_econ(
    rme_files_path: str,
    nsims: int,
    stores: OutputStores,
    ncores=5,
    uncertainty_dict=None,
    metrics=None,
    max_dist=25.0,
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
    stores : OutputStores
        Data class holding output file paths where economic metric files will be stored.
    ncores : int
        Number of cores to sample cost models over.
    uncertainty_dict : dict
        Contains information on what uncertainty types to sample.
    max_dist : float
        Maximum distance between reefs within a "cluster". Total distance to port is calculated as distance
        to port for closest reef cluster + distance between each additional further cluster where distance between
        clusters is calculated as distance between the reefs furthest from port in each cluster.
    """
    nbatches = math.ceil(nsims / ncores)

    economics_spatial_filepath = path_join(THIS_DIR, "datasets", "econ_spatial.csv")

    if metrics is None:
        metrics = [prd.rci, prd.raw_rti, prd.rfi]

    if uncertainty_dict is None:
        uncertainty_dict = prd.default_uncertainty_dict()

    # Create metric datafiles for economics modelling and extract filename for intervention key
    # Files are created separately for each core (as a large number of runs can cause memory issues
    # when calculating metrics due to handling large metrics datacubes)
    int_keys_fn, metric_filepaths = prd.create_economics_metric_files(
        rme_files_path,
        nsims,
        stores,
        nbatches=nbatches,
        ncores=ncores,
        metrics=metrics,
        max_dist=max_dist,
        uncertainty_dict=uncertainty_dict,
        economics_spatial_filepath=economics_spatial_filepath,
    )

    # Post process metrics to be in single file
    for filepaths in metric_filepaths:
        for filetype in ["intervention", "counterfactual"]:
            file_list = [fn for fn in filepaths if filetype in fn]
            post_process_metrics(file_list, metrics, nsims, nbatches)

    return int_keys_fn, nbatches


def post_process_metrics(metric_filepaths, metrics, nsims, nbatches):
    """
    When running multiple cores for cost sampling, metrics calculations are also broken into batches
    to avoid memory issues when creating large metrics datacubes (have shape nsims*nyears*nreefs)

    Writes metric results NOT as a "large metrics datacubes" but as a flat CSV.

    Parameters
    ----------
    metric_filepaths : list{string}
        List of all filepaths where metrics are saved.
    metrics : list{function}
        List of metric functions which were calculated.
    nsims : int
        Total number of simulations runs
    nbatches : int
        Number of samples per core run

    Returns
    -------
    None
    """
    econ_dir = RESULT_DIRS["econ_dir"]

    init_metric_df = pd.read_csv(path_join(econ_dir, metric_filepaths[0]))
    sim_cols = [f"sim_{i}" for i in range(1, nsims + 1)]
    metric_df = pd.DataFrame(
        np.zeros((init_metric_df.shape[0], nsims), dtype=np.float64), columns=sim_cols
    )

    # TODO: Why 0:19? See also indexing with steps of 19 in for loop below?
    metric_df = pd.concat(
        (init_metric_df[init_metric_df.columns[0:19]], metric_df), axis=1
    )

    for metric_f in metrics:
        file_list = [fn for fn in metric_filepaths if metric_f.__name__ in fn]
        for idx_met, metrics_file in enumerate(file_list):
            met_file = path_join(econ_dir, metrics_file)
            met_temp = pd.read_csv(met_file)
            metric_df.iloc[
                :, idx_met * nbatches + 19 : idx_met * nbatches + 19 + nbatches
            ] = met_temp.values[:, 19 : nbatches + 19]
            os.remove(met_file)

        save_fn = file_list[0][:-11] + ".csv"  # TODO: Nicer handling of this "-11"
        out_file = path_join(econ_dir, save_fn)
        metric_df.to_csv(out_file, index=False)


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
        sim_cols = ["year", "component"] + [
            "draw" + str(i) for i in range(1, nsims + 1)
        ]

        cost_df = pd.DataFrame(
            np.zeros((init_cost_df.shape[0], 2 + nsims)), columns=sim_cols
        )
        cost_df.loc[:, ["year", "component"]] = init_cost_df[["year", "component"]]

        save_fn = result[0][iv_id].split("id")[0][:-6] + ".csv"

        for idx_r, res in enumerate(result):
            cost_temp = pd.read_csv(res[iv_id])
            cost_df.iloc[:, idx_r * nbatches + 2 : idx_r * nbatches + 2 + nbatches] = (
                cost_temp.values[:, 2 : nbatches + 2]
            )
            os.remove(res[iv_id])

        cost_df.to_csv(save_fn, index=False)
