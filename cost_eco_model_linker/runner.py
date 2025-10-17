from os.path import join as path_join
from .setup_results import RESULT_DIRS
from . import setup_dirs
from . import create_economics_metric_files
from . import calculate_costs


def evaluate(rme_files_path, nsims, deploy_model_fn, prod_model_fn, results_dir):
    stores = setup_dirs(results_dir)

    # Create metric data files for economics modelling and extract filename for intervention key
    int_keys_fn, _ = create_economics_metric_files(rme_files_path, nsims, stores)

    iv_keys_dir = RESULT_DIRS["intervention_keys_dir"]

    # Create cost data files for the intervention run ids in ID_key
    # Assumes Cost Model spreadsheets are in same directory as this script.
    result_paths = calculate_costs(iv_keys_dir, int_keys_fn, nsims, deploy_model_fn, prod_model_fn)

    return result_paths
