import os
from functools import partial

import re
from packaging.version import Version

import multiprocess as mp

from . import process_RME_data as prd
from .parallel_cost_sampling import post_process_metrics
from .calculate_metrics import default_uncertainty_dict
from . import (
    setup_dirs,
    create_economics_metric_files,
    para_sample_econ,
    calculate_costs,
    post_process_costs,
)

from .handlers import open_excel, close_excel

from .sampling import (
    load_internal_config,
    calculate_production_cost,
    calculate_deployment_cost,
    THIS_DIR,
    DEFAULT_PROD_VER,
    DEFAULT_DEPLOY_VER,
)

import numpy as np
import pandas as pd

SEMVER_RE = re.compile(r"^(?:.*/)?(\d+\.\d+\.\d+)\b")


def evaluate(
    rme_files_path: str,
    nsims: int,
    deploy_model_fn: str,
    prod_model_fn: str,
    results_dir: str,
    metrics: list = None,
    uncertainty_dict: dict = None,
) -> list[str]:
    """
    Evaluate costs of intervention scenarios.

    Parameters
    ----------
    rme_files_path : str
        Path to ReefMod Engine results.
    nsims : int
        Number of simulations to evaluate.
    deploy_model_fn : str
        Path to deployment spreadsheet model, including filename but excluding file extension.
    prod_model_fn : str
        Path to production spreadsheet model, including filename but excluding file extension.
    results_dir : str
        Path to directory for storing results.
    metrics : list, optional
        List of metrics to calculate. Default is None.
    uncertainty_dict : dict, optional
        Dictionary specifying uncertainty parameters. Default is None.

    Returns
    -------
    list[str]
        Paths to result files.
    """
    # Check available config aligns with model versions
    m = SEMVER_RE.match(deploy_model_fn)
    deploy_m_ver = Version(m.group(1)) if m else None
    if deploy_m_ver is None:
        raise ValueError(f"No version info found in filename {deploy_model_fn}")

    m = SEMVER_RE.match(prod_model_fn)
    prod_m_ver = Version(m.group(1)) if m else None
    if prod_m_ver is None:
        raise ValueError(f"No version info found in filename {prod_model_fn}")

    # Check that relevant config files exist
    try:
        load_internal_config(f"{str(deploy_m_ver)}_deploy_config.csv")
    except FileNotFoundError:
        raise ValueError(
            f"No config available for deployment model {str(deploy_m_ver)}"
        )

    try:
        load_internal_config(f"{str(prod_m_ver)}_prod_config.csv")
    except FileNotFoundError:
        raise ValueError(f"No config available for production model {str(prod_m_ver)}")

    # Setup data stores
    stores = setup_dirs(results_dir)

    # Set defaults
    if metrics is None:
        metrics = [prd.rci, prd.raw_rti, prd.rfi]
    if uncertainty_dict is None:
        uncertainty_dict = default_uncertainty_dict()

    # Create metric data files for economics modelling and extract filename for intervention key
    int_keys_fn, metric_fps = create_economics_metric_files(
        rme_files_path,
        nsims,
        stores,
        metrics=metrics,
        uncertainty_dict=uncertainty_dict,
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
    metrics: list = None,
    uncertainty_dict: dict = None,
):
    stores = setup_dirs(results_dir)

    # Set defaults
    if metrics is None:
        metrics = [prd.rci, prd.raw_rti, prd.rfi]
    if uncertainty_dict is None:
        uncertainty_dict = default_uncertainty_dict()

    # Create economics metrics input files, get number of batches needed to complete nsims over ncores
    int_keys_fn, nbatches = para_sample_econ(
        rme_files_path,
        nsims,
        stores,
        ncores=ncores,
        metrics=metrics,
        uncertainty_dict=uncertainty_dict,
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
    post_process_costs(result, nsims)


def evaluate_production_cost(
    workbook_path: str,
    **factors,
) -> tuple[float, float]:
    """
    Wrapper that converts factor kwargs into the format expected by
    calculate_production_cost and returns operational and setup costs.
    Only the factors to be overridden need to be provided; all others
    default to their current values in the workbook.

    Parameters
    ----------
    workbook_path : str
        Absolute path to the Excel workbook.
    **factors
        Factor name-value pairs keyed by factor_name from the config CSV.
        Only factors to be overridden need to be supplied.
        Note: '1YOEC_yield' must be passed as **{"1YOEC_yield": value}
        due to the leading digit making it an invalid Python identifier.

    Returns
    -------
    op_cost : float
        Operational cost.
    setup_cost : float
        Setup cost.
    """
    factor_spec = pd.read_csv(f"{THIS_DIR}/{DEFAULT_PROD_VER}_prod_config.csv")

    unknown_factors = set(factors) - set(factor_spec["factor_names"])
    if unknown_factors:
        raise ValueError(f"Unrecognised factor(s): {unknown_factors}")

    xlapp, wb = open_excel(workbook_path)
    try:
        # Read current cell values from workbook as defaults
        spreadsheet_vals = {}
        for _, row in factor_spec.iterrows():
            cell_value = wb.Sheets(row["sheet"]).Range(row["cell_pos"]).Value
            spreadsheet_vals[row["factor_names"]] = cell_value

        # Override with user-provided values
        spreadsheet_vals.update(factors)

        factors_row = pd.Series(spreadsheet_vals)
        op_cost, setup_cost = calculate_production_cost(wb, factor_spec, factors_row)
    finally:
        close_excel(xlapp, wb)

    return op_cost, setup_cost


def evaluate_deployment_cost(
    workbook_path: str,
    **factors,
) -> tuple[float, float]:
    """
    Wrapper that converts factor kwargs into the format expected by
    calculate_deployment_cost and returns operational and setup costs.
    Only the factors to be overridden need to be provided; all others
    default to their current values in the workbook.

    Parameters
    ----------
    workbook_path : str
        Absolute path to the Excel workbook.
    **factors
        Factor name-value pairs keyed by factor_name from the config CSV.
        Only factors to be overridden need to be supplied.
        Note: '1YOEC_yield' must be passed as **{"1YOEC_yield": value}
        due to the leading digit making it an invalid Python identifier.

    Returns
    -------
    op_cost : float
        Operational cost.
    setup_cost : float
        Setup cost.
    """
    model_spec = pd.read_csv(f"{THIS_DIR}/{DEFAULT_DEPLOY_VER}_deploy_config.csv")

    unknown_factors = set(factors) - set(model_spec["factor_names"])
    if unknown_factors:
        raise ValueError(f"Unrecognised factor(s): {unknown_factors}")

    xlapp, wb = open_excel(workbook_path)
    try:
        # Retrieve reef key list, matching the logic in calculate_deployment_cost
        lookup_ws = wb.Sheets("Lookup Tables")
        start_cell = lookup_ws.Cells.Find("Moore")
        col_num = start_cell.Column
        tbl_region = start_cell.CurrentRegion.Rows
        end_cell_pos = tbl_region.Row + tbl_region.Rows.Count - 1
        end_cell = lookup_ws.Cells(end_cell_pos, col_num)
        reef_key = np.array(lookup_ws.Range(start_cell, end_cell).Value).flatten()

        # Read current cell values from workbook as defaults
        spreadsheet_vals = {}
        for _, row in model_spec.iterrows():
            cell_value = wb.Sheets(row["sheet"]).Range(row["cell_pos"]).Value
            if row["factor_names"] == "reef":
                # Convert string back to 1-based dropdown index
                cell_value = int(np.where(reef_key == cell_value)[0][0]) + 1

            spreadsheet_vals[row["factor_names"]] = cell_value

        # Override with user-provided values
        spreadsheet_vals.update(factors)

        factors_row = pd.Series(spreadsheet_vals)

        # Note: Number of deployed devices get adjusted to obtain the required production
        # volume/yield inside `calculate_deployment_cost()`
        # e.g., to deploy 1M devices with at least 1 coral each, and a yield of 40%,
        # 2.5M corals are needed to be produced.
        op_cost, setup_cost = calculate_deployment_cost(wb, model_spec, factors_row)
    finally:
        close_excel(xlapp, wb)

    return op_cost, setup_cost
