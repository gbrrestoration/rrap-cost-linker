import os
from os.path import join as path_join

import math

from .setup_results import OutputStores
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
        uncertainty_dict=uncertainty_dict,
        economics_spatial_filepath=economics_spatial_filepath,
    )

    # Post process metrics to be in single file
    for filepaths in metric_filepaths:
        for sim_type in ["intervention", "counterfactual"]:
            file_list = [fn for fn in filepaths if sim_type in fn]
            post_process_metrics(stores, file_list, metrics, nsims)

    os.remove(path_join(stores.cost_dir, "sim_template.parq"))

    return int_keys_fn, nbatches


def post_process_metrics(
    stores: OutputStores, metric_filepaths: list[str], metrics: list, nsims: int
):
    """
    When running multiple cores for cost sampling, metrics calculations are also broken into batches
    to avoid memory issues when creating large metrics datacubes (have shape nsims*nyears*nreefs)

    Writes metric results NOT as a "large metrics datacubes" but as a flat CSV.

    Parameters
    ----------
    stores : OutputStore
        Data class defining output directories
    metric_filepaths : list{string}
        List of all filepaths where metrics are saved.
    metrics : list{function}
        List of metric functions which were calculated.
    nsims : int
        Total number of simulations runs

    Returns
    -------
    None
    """
    _metric_dir_map = {
        "rci": stores.rci_dir,
        "rfi": stores.rfi_dir,
        "raw_rti": stores.rti_dir,
    }

    cost_dir = stores.cost_dir
    init_metric_df = pd.read_parquet(path_join(cost_dir, "sim_template.parq"))
    sim_cols = [f"sim_{i}" for i in range(1, nsims + 1)]
    metric_df = pd.DataFrame(
        np.zeros((init_metric_df.shape[0], nsims), dtype=np.float64), columns=sim_cols
    )

    for metric_f in metrics:
        file_list = [fn for fn in metric_filepaths if f"_{metric_f.__name__}_" in fn]
        for metrics_file in file_list:
            met_file = path_join(cost_dir, metrics_file)
            met_temp = pd.read_parquet(met_file)

            metric_data_cols = met_temp.columns
            metric_df[metric_data_cols] = met_temp[metric_data_cols]

        metric_out = pd.concat((init_metric_df, metric_df), axis=1)

        # Extract common part of filename and route to metric-specific directory
        fn = f"{file_list[0].split('_batch')[0]}.parq"
        out_dir = _metric_dir_map.get(metric_f.__name__)
        if out_dir is None:
            raise ValueError(
                f"No output directory configured for metric '{metric_f.__name__}'. "
                f"Known metrics: {list(_metric_dir_map)}"
            )
        out_file = path_join(out_dir, fn)
        metric_out.to_parquet(out_file, index=False)

        for fn in file_list:
            os.remove(path_join(cost_dir, fn))


def post_process_costs(result, nsims):
    """
    Save cost samples run in parallel in a single file which is in the correct format for the economics modelling.

    Parameters
    ----------
    result : list
        List of filenames for saved parallel cost data runs.
    nsims : int
        Total number of draws to sample cost models, should match ecological metrics sampling.
    """
    for iv_id in range(len(result[0])):
        init_cost_df = pd.read_csv(result[0][iv_id])
        save_fn = result[0][iv_id].split("id")[0][:-6] + ".csv"

        chunks = [init_cost_df[["year", "component"]]]
        for res in result:
            cost_temp = pd.read_csv(res[iv_id])
            chunks.append(cost_temp[cost_temp.columns[2:]])  # column id 2 is where data begins
            os.remove(res[iv_id])

        cost_df = pd.concat(chunks, axis=1)
        cost_df.to_csv(save_fn, index=False)
