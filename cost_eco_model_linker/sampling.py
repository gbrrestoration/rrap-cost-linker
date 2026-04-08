import os
from os.path import join as path_join
import tempfile
import shutil
from SALib import ProblemSpec
import multiprocess as mp
import numpy as np
import pandas as pd

import matplotlib.pyplot as plt

from .handlers import open_excel, close_excel, reset_workbook

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROD_VER = "3.9.1"
DEFAULT_DEPLOY_VER = "3.9.0"
DEFAULT_LM_VER = "3.9.6"

LM_REPLACEMENT_RATE = 0.20


def get_NK(
    nsims: int, n_factors: int, calc_second_order: bool = False
) -> tuple[int, int]:
    """
    Calculate the base Sobol' sample count N given a desired total number of
    model evaluations and the number of input factors.

    SALib's Saltelli sampler produces ``N * K`` samples where:
    - ``K = 2 * n_factors + 2`` when ``calc_second_order=True``
    - ``K = n_factors + 2``     when ``calc_second_order=False``

    Returns the smallest N such that ``N * K >= nsims``.

    Parameters
    ----------
    nsims : int
        Desired total number of model evaluations.
    n_factors : int
        Number of input factors (excluding output columns).
    calc_second_order : bool, optional
        Whether second-order indices will be calculated. Must match the value
        passed to ``sample_sobol``. Default False.

    Returns
    -------
    N : int
        Base sample count to pass to ``sample_sobol``.
    K : int
        Saltelli multiplier.
    """
    K = int(2 * n_factors + 2) if calc_second_order else int(n_factors + 2)
    N = int(2 ** np.ceil(np.log2(np.ceil(nsims / K))))
    return N, K


def _read_reef_key(wb) -> np.ndarray:
    """Read reef cluster names from the deployment workbook lookup table."""
    lookup_ws = wb.Sheets("Lookup Tables")
    start_cell = lookup_ws.Cells.Find("Moore")
    col_num = start_cell.Column
    tbl_region = start_cell.CurrentRegion.Rows
    end_cell_pos = tbl_region.Row + tbl_region.Rows.Count - 1
    end_cell = lookup_ws.Cells(end_cell_pos, col_num)
    return np.array(lookup_ws.Range(start_cell, end_cell).Value).flatten()


def evaluate_spreadsheet(wb, model_spec, params) -> tuple[float, float]:
    """
    Set input cells, trigger recalculation, and read back capex and opex.

    This is the inner function for both cost models. All model-specific parameter
    transformations (yield adjustment, reef name resolution, vessel type switching)
    must be applied to `params` before calling this function.

    Parameters
    ----------
    wb : Workbook
        Open Excel workbook.
    model_spec : DataFrame
        Factor specification with columns: factor_names, sheet, cell_pos.
    params : Series
        Fully-resolved parameter values indexed by factor_names.

    Returns
    -------
    capex : float
    opex : float
    """
    factor_names = model_spec.factor_names
    not_costs = ~factor_names.isin(["capex", "opex"])

    xlManual = -4135
    xlAutomatic = -4105
    wb.Application.Calculation = xlManual
    try:
        for _, row in model_spec[not_costs].iterrows():
            wb.Sheets(row.sheet).Range(row.cell_pos).Value = params[row.factor_names]
    finally:
        wb.Application.Calculation = xlAutomatic

    wb.Application.CalculateFull()
    ws = wb.Sheets("Dashboard")

    capex_cell = model_spec.loc[factor_names == "capex", "cell_pos"].values[0]
    opex_cell = model_spec.loc[factor_names == "opex", "cell_pos"].values[0]

    capex_raw = float(ws.Range(capex_cell).Value)
    opex_raw = float(ws.Range(opex_cell).Value)

    # Excel error values are returned as large negative integers by win32com.
    # Any negative output is nonsensical for a cost model, so treat all as errors.
    if capex_raw < 0 or opex_raw < 0:
        raise ValueError(
            f"Negative/error value returned from spreadsheet: capex={capex_raw}, opex={opex_raw}"
        )

    return capex_raw, opex_raw


def calculate_deployment_cost(wb, model_spec, factors):
    """
    Calculates set up and operational costs in the deployment cost model (wb), given a set of parameters to sample.

    Parameters
    ----------
    wb : Workbook
        The cost model as an excel workbook
    model_spec : DataFrame
        The cost model specification, detailing where cells are in the spreadsheet
    factors : DataFrameRow
        Factor values to run cost model with

    Returns
    -------
    capex: float
        Setup cost (CAPEX)
    opex: float
        Operational cost (OPEX)
    """
    if "reef" in factors:
        # Convert 1-based reef index to reef name for cell input
        factors["reef"] = _read_reef_key(wb)[int(factors["reef"]) - 1]

    # if factors["daytrip"] == 1:
    #     factors["daytrip"] = 1

    # Cap distance to the maximum supported by the spreadsheet lookup table.
    factors["distance_from_port"] = min(factors["distance_from_port"], 119.99)

    # If distance exceeds day-trip range, force daytrip=0 regardless of sampled value.
    # This keeps D7 (vessel type selector) and D12 (daytrip flag) consistent.
    if factors["distance_from_port"] > 59:
        factors["daytrip"] = 0

    # Set vessel type cell D7 explicitly every row so state never bleeds across evaluations.
    # 4 = large live-aboard (required when distance > 59NM or not a day-trip), else 1 = day vessel.
    sheet_name = model_spec.loc[
        model_spec.factor_names == "distance_from_port", "sheet"
    ].values[0]
    use_liveaboard = factors["daytrip"] == 0
    wb.Sheets(sheet_name).Range("D7").Value = (
        "Large Liveaboard" if use_liveaboard else "Large Tourism C"
    )

    # Only write the applicable ship parameters to avoid the inactive vessel's values
    # interfering with model formulas and causing div/0 errors.
    # LTC params apply to day trips; LL params apply to liveaboard/overnight trips.
    if use_liveaboard:
        inactive = ["ship_price_LTC", "ship_endurance_LTC"]
    else:
        inactive = ["ship_price_LL", "ship_endurance_LL"]
    active_spec = model_spec[~model_spec.factor_names.isin(inactive)]

    return evaluate_spreadsheet(wb, active_spec, factors)


def calculate_production_cost(wb, factor_spec, factors):
    """
    Calculates set up and operational costs in the production cost model (wb), given a set of parameters to sample.

    Parameters
    ----------
    wb : Workbook
        The cost model as an excel workbook
    factor_spec : DataFrame
        Factor specification, as loaded from the config.csv
    factors : DataFrameRow
        Factor values to run model with

    Returns
    -------
    capex: float
        Setup cost (CAPEX)
    opex: float
        Operational cost (OPEX)
    """
    return evaluate_spreadsheet(wb, factor_spec, factors)


def load_config():
    """
    Load configuration files for model sampling (production, deployment, and LM).
    """
    prod = pd.read_csv(f"{THIS_DIR}/{DEFAULT_PROD_VER}_prod_config.csv")
    deploy = pd.read_csv(f"{THIS_DIR}/{DEFAULT_DEPLOY_VER}_deploy_config.csv")
    lm = pd.read_csv(f"{THIS_DIR}/{DEFAULT_LM_VER}_LM_config.csv")

    return pd.concat([prod, deploy, lm], ignore_index=True)


def load_internal_config(fp):
    """
    Load internal config for model sampling

    Parameters
    ----------
    fp : str
        Filename of config file within the package structure
    """
    return pd.read_csv(os.path.join(THIS_DIR, fp))


# Distributions that use [lower, upper] bounds and support the categorical flooring trick.
# "discrete" is a convenience label in the config meaning uniform over discrete values.
_UNIFORM_LIKE_DISTS = {"unif", "logunif", "discrete"}

# Map convenience/long-form distribution names to SALib distribution codes.
_DIST_ALIASES = {
    "discrete": "unif",  # discrete uniform — treated as continuous uniform by SALib
    "normal": "norm",  # long-form alias
}


def problem_spec(cost_type):
    """
    Create a problem specification for sampling cost models using SALib.

    Parameters
    ----------
    cost_type : str
        String specifying cost model type, "production_params" or "deployment_params"
    config_filepath : str
        String specifying filepath of config file, default is the default package config file

    Returns
    -------
    sp : dict
        ProblemSpec for sampling with SALib
    model_spec : dataframe
        factor specification, as loaded from the config.csv
    """
    if cost_type not in ("production", "deployment", "lm"):
        raise ValueError("Non-existent parameter type")

    model_spec = load_config()

    # Remove results (speaks to where to extract results from, not model factors)
    # and filter down to the desired cost type.
    # not_capex_opex = ~model_spec.factor_names.isin(["capex", "opex"])
    # Turns out this is needed to extract the cell positions from, and why the lower/upper
    # bounds were populated.
    is_cost_type = model_spec.cost_type == cost_type
    model_spec = model_spec[is_cost_type]

    # Remove output from consideration
    not_capex = model_spec.factor_names != "capex"
    not_opex = model_spec.factor_names != "opex"
    sp_spec = model_spec.loc[not_capex & not_opex, :]

    # Resolve sampling distributions: fill missing with "unif"
    raw_dists = sp_spec["UNC_distribution"].fillna("unif").str.strip().str.lower()
    raw_dists = raw_dists.where(raw_dists != "", other="unif")
    is_uniform_like = raw_dists.isin(_UNIFORM_LIKE_DISTS)

    factor_ranges = sp_spec[["range_lower", "range_upper"]].copy()

    # Categorical flooring trick ([min, max+1] then floor) only applies when the
    # distribution is uniform-like; for distributions like "norm" the bounds have a
    # different meaning (e.g. [mean, std]) so we must not modify them.
    is_cat = sp_spec.is_cat
    factor_ranges.loc[is_cat & is_uniform_like, "range_upper"] += 1

    is_discrete_mapped = sp_spec["discrete_values"].notna() & (
        sp_spec["discrete_values"] != ""
    )
    for idx, row in sp_spec[is_discrete_mapped].iterrows():
        options = [float(v) for v in str(row["discrete_values"]).split(",")]
        factor_ranges.loc[idx, "range_lower"] = 0
        factor_ranges.loc[idx, "range_upper"] = len(options)  # flooring trick: [0, n)

    # loguniform requires a strictly positive lower bound
    is_logunif = raw_dists == "logunif"
    factor_ranges.loc[
        is_logunif & (factor_ranges["range_lower"] <= 0), "range_lower"
    ] = 1e-6

    # Map convenience names to SALib distribution codes
    salib_dists = [_DIST_ALIASES.get(d, d) for d in raw_dists]

    problem_dict = {
        "num_vars": sp_spec.shape[0],
        "names": sp_spec.factor_names.to_list(),
        "bounds": factor_ranges.values.tolist(),
        "dists": salib_dists,
    }

    return ProblemSpec(problem_dict), model_spec


def convert_factor_types(factors_df, is_cat):
    """
    SALib samples floats, so convert categorical variables to integers by taking the ceiling.

    Parameters
    ----------
    factors_df : dataframe
        A dataframe of sampled factors
    is_cat : list{bool}
        Boolian vector specifian whether each factor is categorical

    Returns
    -------
    factors_df : Updated sampled factor dataframe with categorical factors as integers
    """
    for ic_ind, ic in enumerate(is_cat):
        if ic:
            factors_df[factors_df.columns[ic_ind]] = np.floor(
                factors_df[factors_df.columns[ic_ind]]
            ).astype(int)

    return factors_df


def apply_discrete_mapping(factors_df, model_spec):
    """
    Map sampled integer indices back to their actual discrete values.
    Only applies to factors with a discrete_values entry in model_spec.
    Factors marked as is_cat without discrete_values are already handled
    by the flooring trick in convert_factor_types.

    Parameters
    ----------
    factors_df : dataframe
        A dataframe of sampled factors
    model_spec : dataframe
        Factor specification, as loaded from the config CSV

    Returns
    -------
    factors_df : Updated sampled factor dataframe with discrete mappings applied

    Raises
    ------
    ValueError
        If the min/max of discrete_values does not match range_lower/range_upper
    """
    for _, row in model_spec.iterrows():
        if pd.notna(row["discrete_values"]) and row["discrete_values"] != "":
            options = [float(v) for v in str(row["discrete_values"]).split(",")]

            if min(options) != row["range_lower"] or max(options) != row["range_upper"]:
                raise ValueError(
                    f"discrete_values for '{row['factor_names']}' has min/max "
                    f"({min(options)}, {max(options)}) that does not match "
                    f"range_lower/range_upper ({row['range_lower']}, {row['range_upper']})"
                )

            factors_df[row["factor_names"]] = factors_df[row["factor_names"]].apply(
                lambda idx: options[int(idx)]
            )

    return factors_df


def _com_retry(fn, retries=3, delay=2.0):
    """Call ``fn()`` retrying on COM/RPC failures up to ``retries`` times."""
    import time
    import pywintypes

    for attempt in range(retries):
        try:
            return fn()
        except (pywintypes.com_error, AttributeError):
            if attempt == retries - 1:
                raise
            time.sleep(delay * (attempt + 1))


def _run_cost_model(xlapp, wb, wb_path, cost_factors, factor_spec, calculate_cost):
    """
    Run and collect results from a cost model.

    Parameters
    ----------
    xlapp :
        Excel application instance (used for workbook reset between rows)
    wb :
        Open Excel workbook
    wb_path : str
        Path to the workbook file (used for reset)
    cost_factors : dataframe
        Dataframe of factors to input in the cost model
    factor_spec : dataframe
        factor specification, as loaded from the config.csv
    calculate_cost: function
        Function to use to sample cost. One of:
        - "calculate_deployment_cost"
        - "calculate_production_cost"

    Returns
    -------
    cost_factors : dataframe
        Updated dataframe with costs added
    """
    # Build a best-point baseline from the config to seed the workbook into a known-good
    # state before each row's sampled values are applied.
    not_output = ~factor_spec.factor_names.isin(["capex", "opex"])
    best_point = factor_spec[not_output].set_index("factor_names")["best_point_value"]

    def _seed_workbook(wb):
        xlManual = -4135
        xlAutomatic = -4105
        wb.Application.Calculation = xlManual
        try:
            for fname, value in best_point.items():
                row = factor_spec.loc[factor_spec.factor_names == fname].iloc[0]
                wb.Sheets(row.sheet).Range(row.cell_pos).Value = value
        finally:
            wb.Application.Calculation = xlAutomatic

    total_cost = np.full((cost_factors.shape[0], 2), np.nan)
    for idx_n in range(len(total_cost)):
        _com_retry(lambda: _seed_workbook(wb))
        row_params = cost_factors.iloc[idx_n, :]
        try:
            total_cost[idx_n, :] = _com_retry(
                lambda: calculate_cost(wb, factor_spec, row_params)
            )
        except ValueError as e:
            import warnings

            warnings.warn(
                f"Row {idx_n} skipped in '{os.path.basename(wb_path)}' — {e}. Params: {row_params.to_dict()}"
            )
        if idx_n < len(total_cost) - 1:
            wb = _com_retry(lambda: reset_workbook(xlapp, wb, wb_path))

    try:
        cost_factors.loc[:, ["capex", "opex"]] = total_cost
        cost_factors["total_cost"] = cost_factors["capex"] + cost_factors["opex"]
    except TypeError:
        raise TypeError(
            "Incorrect type encountered. Ensure continuous values are not integers in config files."
        )

    return wb, cost_factors


def collect_production_costs(xlapp, wb, wb_path, cost_factors, factor_spec):
    """
    Run the production cost model.

    Parameters
    ----------
    xlapp :
        Excel application instance
    wb :
        Open Excel workbook
    wb_path : str
        Path to the workbook file
    cost_factors : dataframe
        Dataframe of factors to input in the cost model
    factor_spec : dataframe
        Factor specification, as loaded from the config.csv

    Returns
    -------
    wb :
        Updated workbook reference (may differ from input if resets occurred internally).
    cost_factors : dataframe
        Updated sampled factor dataframe with costs added
    """
    return _run_cost_model(
        xlapp, wb, wb_path, cost_factors, factor_spec, calculate_production_cost
    )


def collect_deployment_costs(xlapp, wb, wb_path, cost_factors, factor_spec):
    """
    Run the deployment cost model.

    Parameters
    ----------
    xlapp :
        Excel application instance
    wb :
        Open Excel workbook
    wb_path : str
        Path to the workbook file
    cost_factors : dataframe
        Dataframe of factors to input in the cost model
    factor_spec : dataframe
        Factor specification, as loaded from the config.csv

    Returns
    -------
    wb :
        Updated workbook reference (may differ from input if resets occurred internally).
    cost_factors : dataframe
        Updated sampled factor dataframe with costs added
    """
    return _run_cost_model(
        xlapp, wb, wb_path, cost_factors, factor_spec, calculate_deployment_cost
    )


def calculate_lm_cost(wb, factor_spec, factors):
    """
    Calculates setup and operational costs in the LM (Larval Methods) cost model.

    Parameters
    ----------
    wb : Workbook
        Open Excel workbook.
    factor_spec : DataFrame
        Factor specification, as loaded from the config CSV.
    factors : DataFrameRow
        Factor values to run model with.

    Returns
    -------
    capex : float
    opex : float
    """
    return evaluate_spreadsheet(wb, factor_spec, factors)


def collect_lm_costs(xlapp, wb, wb_path, cost_factors, factor_spec):
    """
    Run the LM cost model.

    Parameters
    ----------
    xlapp :
        Excel application instance.
    wb :
        Open Excel workbook.
    wb_path : str
        Path to the workbook file.
    cost_factors : DataFrame
        Dataframe of factors to input in the cost model.
    factor_spec : DataFrame
        Factor specification, as loaded from the config CSV.

    Returns
    -------
    wb :
        Updated workbook reference (may differ from input if resets occurred internally).
    cost_factors : DataFrame
        Updated sampled factor dataframe with costs added.
    """
    return _run_cost_model(
        xlapp, wb, wb_path, cost_factors, factor_spec, calculate_lm_cost
    )


def _apply_lm_inventory_model(
    df: pd.DataFrame, replacement_rate: float = LM_REPLACEMENT_RATE
) -> pd.DataFrame:
    """
    Apply the LM year-by-year inventory and replacement model to a YearTable.

    For each year t the model:
      1. Allows up to ``replacement_rate`` of last year's inventory to retire.
      2. Replaces as much retired capacity as needed to reach the required capex.
      3. Fills any remaining gap with new (scaling) capex.
      4. Ends the year exactly at the required capex level.

    Year 1 is treated as the initial installed base (no spend tracked separately).

    Parameters
    ----------
    df : pd.DataFrame
        YearTable from the LM workbook; must have ``capex``, ``opex``, and
        ``corals`` columns.
    replacement_rate : float
        Maximum fraction of prior-year inventory that may retire each year.
        Default is ``LM_REPLACEMENT_RATE`` (0.20).

    Returns
    -------
    pd.DataFrame
        Input DataFrame extended with columns: ``inventory``,
        ``new_capex_scale``, ``new_capex_replacement``, ``total_capex``,
        ``total_capex_opex``, ``ratio``, ``average``.
    """
    T = len(df)
    inventory_vec = np.zeros(T)
    new_capex_scale_vec = np.zeros(T)
    new_capex_replacement_vec = np.zeros(T)
    total_capex_vec = np.zeros(T)

    for t in range(T):
        req = float(df["capex"].iloc[t])

        if t == 0:
            inventory_now = req
            new_capex_replacement = 0.0
            new_capex_scale = req
        else:
            I0 = inventory_vec[t - 1]
            retire_capacity = replacement_rate * I0
            survivors = (1.0 - replacement_rate) * I0
            replaced_dollars = max(0.0, min(retire_capacity, req - survivors))
            inventory_after_repl = survivors + replaced_dollars
            new_capex_scale = max(0.0, req - inventory_after_repl)
            inventory_now = inventory_after_repl + new_capex_scale
            new_capex_replacement = replaced_dollars

        inventory_vec[t] = inventory_now
        new_capex_scale_vec[t] = new_capex_scale
        new_capex_replacement_vec[t] = new_capex_replacement
        total_capex_vec[t] = new_capex_replacement + new_capex_scale

    out = df.copy()
    out["inventory"] = inventory_vec
    out["new_capex_scale"] = new_capex_scale_vec
    out["new_capex_replacement"] = new_capex_replacement_vec
    out["total_capex"] = total_capex_vec
    out["total_capex_opex"] = out["total_capex"] + out["opex"]

    total_corals = out["corals"].sum()
    out["ratio"] = (
        out["total_capex_opex"].sum() / total_corals if total_corals > 0 else np.nan
    )
    out["average"] = out["total_capex_opex"].mean()

    return out


def _draw_samples(sp, sample_config, nsims):
    """
    Return a DataFrame of parameter samples for a cost model.

    When ``nsims`` is ``None`` or ``1``, skips Sobol' sampling and returns a
    single row of ``best_point_value`` entries instead.

    Parameters
    ----------
    sp : SALib ProblemSpec
        Problem specification (from ``problem_spec()``).
    sample_config : DataFrame
        Factor specification rows with ``best_point_value`` and ``is_cat`` columns
        (capex/opex rows excluded).
    nsims : int or None
        Desired number of samples.  ``None`` or ``1`` triggers best-point mode.

    Returns
    -------
    samples : DataFrame
        One row per sample, columns matching factor names.
    """
    if nsims is None or nsims == 1:
        samples = pd.DataFrame(
            [dict(zip(sample_config.factor_names, sample_config.best_point_value))]
        )
        return convert_factor_types(samples, sample_config.is_cat)

    N, _ = get_NK(nsims, sp["num_vars"])
    sp.sample_sobol(N, calc_second_order=False)
    samples = pd.DataFrame(data=sp.samples, columns=sp["names"])
    samples = convert_factor_types(samples, sample_config.is_cat)
    samples = apply_discrete_mapping(samples, sample_config)
    return samples


def run_lm_model(cost_model: str, nsims: int, nprocs: int = 1):
    """
    Generate Sobol' samples for the LM model and run.

    Parameters
    ----------
    cost_model : str
        Path to the LM cost model workbook, including extension (.xlsx).
    nsims : int
        Desired total number of model evaluations.
    nprocs : int, optional
        Number of parallel worker processes. Values <= 1 run serially. Default 1.

    Returns
    -------
    SALib ProblemSpec with ``cost_model_results`` added as a field.
    """
    sp, model_config = problem_spec("lm")
    sample_config = model_config.loc[~model_config.factor_names.isin(["capex", "opex"])]

    samples = _draw_samples(sp, sample_config, nsims)

    if nprocs > 1:
        idx_chunks = np.array_split(np.arange(len(samples)), nprocs)
        chunks = [samples.iloc[idx] for idx in idx_chunks if len(idx) > 0]
        tmp_paths = _make_temp_copies(cost_model, len(chunks))
        try:
            args = [
                (p, model_config, collect_lm_costs, c)
                for p, c in zip(tmp_paths, chunks)
            ]
            _fix_main_spec()
            with mp.Pool(nprocs, initializer=_pool_initializer) as pool:
                results = pool.starmap(_run_chunk_on_copy, args)
            sample_w_cost_results = pd.concat(results, ignore_index=True)
        finally:
            for p in tmp_paths:
                os.remove(p)
    else:
        tmp_paths = _make_temp_copies(cost_model, 1)
        try:
            sample_w_cost_results = _run_chunk_on_copy(
                tmp_paths[0], model_config, collect_lm_costs, samples
            )
        finally:
            os.remove(tmp_paths[0])

    sp["cost_model_results"] = sample_w_cost_results
    return sp


def _fix_main_spec():
    """Ensure __spec__ is set on __main__ before spawning workers on Windows.

    multiprocess's spawn.py does `getattr(main.__spec__, 'name', None)` which
    raises AttributeError if __spec__ doesn't exist (e.g. when running a script
    directly). Must be called in the *main* process before Pool is created.
    """
    import sys

    main = sys.modules.get("__main__")
    if main is not None and not hasattr(main, "__spec__"):
        main.__spec__ = None


def _pool_initializer():
    """Initialise each worker process."""
    _fix_main_spec()
    # Switch to a non-interactive backend so that tkinter is never imported in
    # worker processes. Without this, tkinter objects inherited from the main
    # process are garbage-collected in worker threads, raising
    # "RuntimeError: main thread is not in main loop" on the second parallel run.
    import matplotlib

    matplotlib.use("Agg")


def _run_chunk_on_copy(tmp_path, model_config, collect_fn, samples_chunk):
    """Worker: evaluate a chunk of samples on a pre-created temp workbook copy."""
    xlapp, wb = open_excel(tmp_path)
    try:
        wb, result = collect_fn(xlapp, wb, tmp_path, samples_chunk, model_config)
        return result
    finally:
        close_excel(xlapp, wb)


def _make_temp_copies(cost_model, n):
    """Create n temporary copies of cost_model in the main process. Returns list of paths."""
    base, ext = os.path.splitext(cost_model)
    tmp_paths = []
    for _ in range(n):
        tmp_fd, tmp_path = tempfile.mkstemp(
            suffix=ext, prefix=os.path.basename(base) + "_"
        )
        os.close(tmp_fd)
        shutil.copy(cost_model, tmp_path)
        tmp_paths.append(tmp_path)
    return tmp_paths


def run_deployment_model(cost_model: str, nsims: int, nprocs: int = 1):
    """
    Generate Sobol' samples for the deployment model and run.

    Parameters
    ----------
    cost_model : str
        Path to cost (spreadsheet) model
    nsims : int
        Desired total number of model evaluations. The base Sobol' sample count
        N is derived via ``get_NK(nsims, n_factors)``, giving ``N*(2D+2)``
        actual evaluations (the closest multiple >= nsims).
    nprocs : int, optional
        Number of parallel worker processes. Values <= 1 run serially. Default 1.

    Returns
    -------
    SALib ProblemSpec with `cost_model_results` added as a field.
    """
    sp, model_config = problem_spec("deployment")
    sample_config = model_config.loc[~model_config.factor_names.isin(["capex", "opex"])]

    samples = _draw_samples(sp, sample_config, nsims)

    if nprocs > 1:
        idx_chunks = np.array_split(np.arange(len(samples)), nprocs)
        chunks = [samples.iloc[idx] for idx in idx_chunks if len(idx) > 0]
        tmp_paths = _make_temp_copies(cost_model, len(chunks))
        try:
            args = [
                (p, model_config, collect_deployment_costs, c)
                for p, c in zip(tmp_paths, chunks)
            ]
            _fix_main_spec()
            with mp.Pool(nprocs, initializer=_pool_initializer) as pool:
                results = pool.starmap(_run_chunk_on_copy, args)
            sample_w_cost_results = pd.concat(results, ignore_index=True)
        finally:
            for p in tmp_paths:
                os.remove(p)
    else:
        tmp_paths = _make_temp_copies(cost_model, 1)
        try:
            sample_w_cost_results = _run_chunk_on_copy(
                tmp_paths[0], model_config, collect_deployment_costs, samples
            )
        finally:
            os.remove(tmp_paths[0])

    sp["cost_model_results"] = sample_w_cost_results
    return sp


def run_production_model(cost_model: str, nsims: int, nprocs: int = 1):
    """
    Generate Sobol' samples for the production model and run.

    Parameters
    ----------
    cost_model : str
        Path to cost (spreadsheet) model, including extension (.xlsx)
    nsims : int
        Desired total number of model evaluations. The base Sobol' sample count
        N is derived via ``get_NK(nsims, n_factors)``, giving ``N*(2D+2)``
        actual evaluations (the closest multiple >= nsims).
    nprocs : int, optional
        Number of parallel worker processes. Values <= 1 run serially. Default 1.

    Returns
    -------
    SALib ProblemSpec with `cost_model_results` added as a field.
    """
    sp, model_config = problem_spec("production")
    sample_config = model_config.loc[~model_config.factor_names.isin(["capex", "opex"])]

    samples = _draw_samples(sp, sample_config, nsims)

    if nprocs > 1:
        idx_chunks = np.array_split(np.arange(len(samples)), nprocs)
        chunks = [samples.iloc[idx] for idx in idx_chunks if len(idx) > 0]
        tmp_paths = _make_temp_copies(cost_model, len(chunks))
        try:
            args = [
                (p, model_config, collect_production_costs, c)
                for p, c in zip(tmp_paths, chunks)
            ]
            _fix_main_spec()
            with mp.Pool(nprocs, initializer=_pool_initializer) as pool:
                results = pool.starmap(_run_chunk_on_copy, args)
            sample_w_cost_results = pd.concat(results, ignore_index=True)
        finally:
            for p in tmp_paths:
                os.remove(p)
    else:
        tmp_paths = _make_temp_copies(cost_model, 1)
        try:
            sample_w_cost_results = _run_chunk_on_copy(
                tmp_paths[0], model_config, collect_production_costs, samples
            )
        finally:
            os.remove(tmp_paths[0])

    sp["cost_model_results"] = sample_w_cost_results
    return sp


def extract_sa_results(sp: ProblemSpec, fig_path: str = "./figs/"):
    """
    Run PAWN sensitivity analysis on cost model results and save figures.

    Parameters
    ----------
    sp : ProblemSpec
        Must have ``sp["cost_model_results"]`` set to a DataFrame with columns
        matching ``sp["names"]`` plus ``"capex"`` and ``"opex"``.
        Use ``sp["cost_model_results"] = results_df`` to attach results from
        ``run_joint_cost_models`` before calling this function.
    fig_path : str
        Directory where figures are saved.
    """
    os.makedirs(fig_path, exist_ok=True)

    cost_results = sp["cost_model_results"]

    def _analyze(output_col, label):
        # Do not call set_samples() — the Sobol' samples are already in sp.samples
        # from sample_sobol(), and replacing them resets SALib's internal
        # calc_second_order flag to True, causing plot() to include S2.
        sp.set_results(np.array(cost_results[output_col]))

        sp.analyze_sobol(calc_second_order=False)
        sp.plot()
        fig = plt.gcf()
        fig.set_size_inches(10, 4)
        plt.tight_layout()
        plt.savefig(path_join(fig_path, f"{label}_sobol_SA.png"), bbox_inches="tight")
        plt.close()

        sp.analyze_pawn()
        axes = sp.plot()
        fig = plt.gcf()
        fig.set_size_inches(10, 4)
        # Move the legend outside the figure to the right.
        ax_last = axes[-1] if hasattr(axes, "__len__") else axes
        legend = ax_last.get_legend()
        if legend is not None:
            ax_last.legend(
                handles=legend.legend_handles,
                labels=[t.get_text() for t in legend.get_texts()],
                loc="upper left",
                bbox_to_anchor=(1.01, 1),
                borderaxespad=0,
            )
        plt.tight_layout()
        plt.savefig(
            path_join(fig_path, f"{label}_pawn_barplot_SA.png"), bbox_inches="tight"
        )
        plt.close()

        sp.heatmap()
        fig = plt.gcf()
        fig.set_size_inches(10, 4)
        plt.savefig(
            path_join(fig_path, f"{label}_pawn_heatmap_SA.png"), bbox_inches="tight"
        )
        plt.close()

    _analyze("capex", "setup_cost")
    _analyze("opex", "operational_cost")
    _analyze("total_cost", "total_cost")
