import os
from functools import partial
import shutil
import tempfile

import re
from packaging.version import Version

import numpy as np
import pandas as pd
# from SALib import ProblemSpec

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

from .handlers import open_excel, close_excel, reset_workbook

from .sampling import (
    load_internal_config,
    calculate_production_cost,
    calculate_deployment_cost,
    _read_reef_key,
    THIS_DIR,
)

import numpy as np
import pandas as pd

SEMVER_RE = re.compile(r"^(?:.*/)?(\d+\.\d+\.\d+)\b")

_KNOWN_MODEL_TYPES = {
    "production": "prod",
    "deployment": "deploy",
}


def _parse_model_info(
    workbook_path: str,
    model_type: str | None = None,
) -> tuple[str, str]:
    """
    Extract model type and version from a workbook filename.

    The expected filename pattern is ``'<version> <type> <name>'``,
    e.g. ``'3.9.1 CA Production Model.xlsx'``.

    Parameters
    ----------
    workbook_path : str
        Path to the workbook (only the filename stem is inspected).
    model_type : str, optional
        If provided, skips type inference and only extracts the version.

    Returns
    -------
    model_type : str
        ``"production"`` or ``"deployment"``.
    version : str
        Semantic version string, e.g. ``"3.9.1"``.

    Raises
    ------
    ValueError
        If the version cannot be extracted, or if ``model_type`` is ``None``
        and the type cannot be inferred from the filename.
    """
    stem = os.path.splitext(os.path.basename(workbook_path))[0]

    m = re.search(r"\d+\.\d+\.\d+", stem)
    if not m:
        raise ValueError(
            f"Could not extract a version number from filename {stem!r}. "
            "Expected pattern: '<version> <type> <name>', "
            "e.g. '3.9.1 CA Production Model.xlsx'."
        )
    version = m.group(0)

    if model_type is None:
        stem_lower = stem.lower()
        for name in _KNOWN_MODEL_TYPES:
            if name in stem_lower:
                model_type = name
                break
        else:
            raise ValueError(
                f"Could not infer model type from filename {stem!r}. "
                f"Expected one of {list(_KNOWN_MODEL_TYPES)} in the filename, "
                "or pass model_type explicitly."
            )
    elif model_type not in _KNOWN_MODEL_TYPES:
        raise ValueError(
            f"Unknown model_type {model_type!r}. "
            f"Must be one of {list(_KNOWN_MODEL_TYPES)}."
        )

    return model_type, version


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
        Absolute path to the Excel workbook including extension (.xlsx).
    **factors
        Factor name-value pairs keyed by factor_name from the config CSV.
        Only factors to be overridden need to be supplied.

    Returns
    -------
    op_cost : float
        Operational cost.
    setup_cost : float
        Setup cost.
    """
    _, version = _parse_model_info(workbook_path, "production")
    factor_spec = pd.read_csv(os.path.join(THIS_DIR, f"{version}_prod_config.csv"))

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
        capex, opex = calculate_production_cost(wb, factor_spec, factors_row)
    finally:
        close_excel(xlapp, wb)

    return capex, opex


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
        due to the leading digit making it an invalid Python identifier.

    Returns
    -------
    op_cost : float
        Operational cost.
    setup_cost : float
        Setup cost.
    """
    _, version = _parse_model_info(workbook_path, "deployment")
    model_spec = pd.read_csv(os.path.join(THIS_DIR, f"{version}_deploy_config.csv"))

    unknown_factors = set(factors) - set(model_spec["factor_names"])
    if unknown_factors:
        raise ValueError(f"Unrecognised factor(s): {unknown_factors}")

    xlapp, wb = open_excel(workbook_path)
    try:
        reef_key = _read_reef_key(wb)

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
        capex, opex = calculate_deployment_cost(wb, model_spec, factors_row)
    finally:
        close_excel(xlapp, wb)

    return capex, opex


# --------------------------------------------------------------------------
# Outer function: temp copy + batch evaluation
# --------------------------------------------------------------------------


def run_cost_model(
    workbook_path: str,
    params_df: pd.DataFrame,
    *,
    model_type: str | None = None,
    nprocs: int | None = None,
) -> pd.DataFrame:
    """
    Evaluate a cost model over a set of parameter combinations.

    The model type (production or deployment) and config version are inferred
    from the workbook filename — e.g. ``'3.9.1 CA Production Model.xlsx'``.
    Pass ``model_type`` explicitly only when the filename does not follow the
    standard naming convention.

    When ``nprocs`` is greater than 1, ``params_df`` is split into chunks and
    evaluated in parallel — each worker opens its own temporary workbook copy.
    Otherwise the whole DataFrame is evaluated serially in a single workbook
    session.

    Columns not present in ``params_df`` default to the values currently in the
    workbook.

    Parameters
    ----------
    workbook_path : str
        Absolute path to the Excel workbook including extension (.xlsx).
    params_df : pd.DataFrame
        Each row is one model evaluation. Column names must be factor names from
        the relevant config CSV. Only factors to be overridden from workbook
        defaults need to be included.
    model_type : str, optional
        ``"production"`` or ``"deployment"``. Inferred from the filename if
        not provided.
    nprocs : int, optional
        Number of parallel worker processes. Values <= 1 run serially.
        Defaults to serial (``None``).

    Returns
    -------
    pd.DataFrame
        Input DataFrame with three appended columns: ``capex``, ``opex``,
        and ``total_cost``.
    """
    model_type, version = _parse_model_info(workbook_path, model_type)

    if nprocs is not None and nprocs > 1:
        chunks = [c for c in np.array_split(params_df, nprocs) if len(c) > 0]
        worker = partial(run_cost_model, workbook_path, model_type=model_type)
        with mp.Pool(processes=nprocs) as pool:
            results = pool.map(worker, chunks)
        return pd.concat(results, ignore_index=True)

    config_suffix = _KNOWN_MODEL_TYPES[model_type]
    evaluate_fn = (
        calculate_production_cost if model_type == "production" else calculate_deployment_cost
    )
    model_spec = pd.read_csv(os.path.join(THIS_DIR, f"{version}_{config_suffix}_config.csv"))

    unknown = set(params_df.columns) - set(model_spec["factor_names"])
    if unknown:
        raise ValueError(f"Unrecognised factor(s): {unknown}")

    base, ext = os.path.splitext(workbook_path)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix=os.path.basename(base) + "_")
    os.close(tmp_fd)

    try:
        shutil.copy(workbook_path, tmp_path)
        xlapp, wb = open_excel(tmp_path)
        try:
            # Read workbook defaults once before any cells are changed
            defaults = {}
            for _, row in model_spec.iterrows():
                defaults[row["factor_names"]] = (
                    wb.Sheets(row["sheet"]).Range(row["cell_pos"]).Value
                )

            # For deployment, the reef cell holds a name; convert to 1-based index
            # so it matches the integer representation used by calculate_deployment_cost
            if model_type == "deployment":
                reef_key = _read_reef_key(wb)
                reef_name = defaults.get("reef")
                if reef_name is not None:
                    defaults["reef"] = int(np.where(reef_key == reef_name)[0][0]) + 1

            results = np.zeros((len(params_df), 2))
            for i, (_, row) in enumerate(params_df.iterrows()):
                params = pd.Series({**defaults, **row.to_dict()})
                results[i] = evaluate_fn(wb, model_spec, params)
                if i < len(params_df) - 1:
                    wb = reset_workbook(xlapp, wb, tmp_path)
        finally:
            close_excel(xlapp, wb)
    finally:
        os.remove(tmp_path)

    return params_df.assign(
        capex=results[:, 0],
        opex=results[:, 1],
        total_cost=results[:, 0] + results[:, 1],
    )


def run_parameter_sweep(
    prod_model,
    deploy_model,
    sweep_param,
    search_range,
    prod_params=None,
    dep_params=None,
):
    """
    Run a parameter sweep over a range of values for any single parameter.

    Parameters
    ----------
    prod_model : model
        Production cost model
    deploy_model : model
        Deployment cost model
    sweep_param : str
        Name of the parameter to sweep over
    search_range : iterable
        Range of values to sweep over for sweep_param
    prod_params : dict, optional
        Fixed keyword arguments passed to evaluate_production_cost
    dep_params : dict, optional
        Fixed keyword arguments passed to evaluate_deployment_cost

    Returns
    -------
    search_range : iterable
        The input search range
    prod_capex : np.ndarray
    prod_opex : np.ndarray
    dep_capex : np.ndarray
    dep_opex : np.ndarray
    totals : np.ndarray
    """
    prod_params = prod_params or {}
    dep_params = dep_params or {}

    prod_sweep = pd.DataFrame([{sweep_param: val, **prod_params} for val in search_range])
    dep_sweep = pd.DataFrame([{sweep_param: val, **dep_params} for val in search_range])

    prod_results = run_cost_model(prod_model, prod_sweep)
    dep_results = run_cost_model(deploy_model, dep_sweep)

    return pd.DataFrame(
        {
            "search_range": search_range,
            "prod_capex": prod_results["capex"].values,
            "prod_opex": prod_results["opex"].values,
            "dep_capex": dep_results["capex"].values,
            "dep_opex": dep_results["opex"].values,
            "totals": prod_results["total_cost"].values + dep_results["total_cost"].values,
        }
    )
