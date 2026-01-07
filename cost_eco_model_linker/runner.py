import os
from functools import partial

import multiprocess as mp

from . import process_RME_data as prd
from .parallel_cost_sampling import post_process_metrics
from . import (
    setup_dirs,
    create_economics_metric_files,
    para_sample_econ,
    calculate_costs,
    post_process_costs,
)


def evaluate(
    rme_files_path: str,
    nsims: int,
    deploy_model_fn: str,
    prod_model_fn: str,
    results_dir: str,
    metrics: list = None,
) -> list[str]:
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

    if metrics is None:
        metrics = [prd.rci, prd.raw_rti, prd.rfi]

    # Create metric data files for economics modelling and extract filename for intervention key
    int_keys_fn, metric_fps = create_economics_metric_files(
        rme_files_path, nsims, stores, metrics=metrics
    )

    # Post process metrics to be in single file
    for filepaths in metric_fps:
        for filetype in ["intervention", "counterfactual"]:
            file_list = [fn for fn in filepaths if filetype in fn]
            post_process_metrics(stores, file_list, metrics, nsims)

    os.remove(os.path.join(stores.econ_dir, "sim_template.parq"))

    # Create cost data files for the intervention run ids in ID_key
    result_paths = calculate_costs(
        stores, int_keys_fn, nsims, deploy_model_fn, prod_model_fn
    )

    return result_paths


def parallel_evaluate(
    rme_files_path: str,
    nsims: int,
    ncores: int,
    deploy_model_fn: str,
    prod_model_fn: str,
    results_dir: str,
):
    stores = setup_dirs(results_dir)

    # Create economics metrics input files, get number of batches needed to complete nsims over ncores
    int_keys_fn, nbatches = para_sample_econ(
        rme_files_path, nsims, stores, ncores=ncores
    )

    # Run cost sampling in parallel on ncores
    with mp.Pool(ncores) as pool:
        wrapper = partial(
            calculate_costs,
            stores,
            int_keys_fn,
            nbatches,
            deploy_model_fn,
            prod_model_fn,
            0.25,  # cont_p
        )
        result = pool.map(wrapper, range(nbatches + 1))

    # Post-process saved samples to be in single file
    post_process_costs(result, nbatches, nsims)
