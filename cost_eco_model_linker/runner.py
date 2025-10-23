import os
from os.path import join as path_join
from functools import partial

import multiprocess as mp

from .setup_results import RESULT_DIRS
from . import setup_dirs
from . import create_economics_metric_files
from . import calculate_costs
from . import para_sample_econ, calc_costs_para, post_process_costs


THIS_DIR = os.path.dirname(__file__)


def evaluate(rme_files_path: str, nsims: int, deploy_model_fn: str, prod_model_fn: str, results_dir: str) -> list[str]:
    """
    Evaluate costs of intervention scenarios.

    Parameters
    ----------
    rme_files_path : str, Path to ReefMod Engine results
    nsims : int, number of simulations to evaluate
    deploy_model_fn : str, Path to deployment (spreadsheet) model (including filename but excluding file extension)
    prod_model_fn : str, Path to production (spreadsheet) model (including filename but excluding file extension)
    results_dir : path to place results

    Returns
    list, result paths
    """
    stores = setup_dirs(results_dir)

    # Create metric data files for economics modelling and extract filename for intervention key
    int_keys_fn, _ = create_economics_metric_files(rme_files_path, nsims, stores)

    iv_keys_dir = RESULT_DIRS["intervention_keys_dir"]

    # Create cost data files for the intervention run ids in ID_key
    # Assumes Cost Model spreadsheets are in same directory as this script.
    result_paths = calculate_costs(iv_keys_dir, int_keys_fn, nsims, deploy_model_fn, prod_model_fn)

    return result_paths


def parallel_evaluate(
    rme_files_path: str,
    nsims: int,
    ncores: int,
    deploy_model_fn: str,
    prod_model_fn: str,
    results_dir: str
):
    stores = setup_dirs(results_dir)

    # Create economics metrics input files, get number of batches needed to complete nsims over ncores
    int_keys_fn, nbatches = para_sample_econ(
        rme_files_path,
        nsims,
        stores,
        ncores=ncores
    )

    # Run cost sampling in parallel on ncores
    if __name__ == "__main__":
        with mp.Pool(ncores) as pool:
            wrapper = partial(
                calc_costs_para,
                int_keys_fn, nbatches, deploy_model_fn, prod_model_fn
            )
            result = pool.map(wrapper, range(ncores))

        # Post-process saved samples to be in single file
        post_process_costs(result, nbatches, nsims)
