import os
from os.path import join as path_join
import tempfile
import shutil
from win32com import client as w32client
from SALib import ProblemSpec
import numpy as np
import pandas as pd

import matplotlib.pyplot as plt

from .handlers import open_excel, close_excel

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROD_VER = "3.9.1"
DEFAULT_DEPLOY_VER = "3.9.0"


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

    for _, row in model_spec[not_costs].iterrows():
        wb.Sheets(row.sheet).Range(row.cell_pos).Value = params[row.factor_names]

    wb.Application.CalculateFull()
    ws = wb.Sheets("Dashboard")

    capex_cell = model_spec.loc[factor_names == "capex", "cell_pos"].values[0]
    opex_cell = model_spec.loc[factor_names == "opex", "cell_pos"].values[0]

    capex_raw = ws.Range(capex_cell).Value
    opex_raw = ws.Range(opex_cell).Value

    if (capex_raw == -2146826281) or (opex_raw == -2146826281):
        raise ValueError("Division by zero error in spreadsheet!")

    return float(capex_raw), float(opex_raw)


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
    params = factors.copy()

    if "reef" in params:
        # Convert 1-based reef index to reef name for cell input
        params["reef"] = _read_reef_key(wb)[int(params["reef"]) - 1]

    # Switch to large live-aboard vessel if distance > 59NM or not a day-trip.
    # D7 is set before evaluate_spreadsheet runs CalculateFull.
    if (params["distance_from_port"] > 59) or (params["daytrip"] == 0):
        sheet_name = model_spec.loc[
            model_spec.factor_names == "distance_from_port", "sheet"
        ].values[0]
        wb.Sheets(sheet_name).Range("D7").Value = 4

    return evaluate_spreadsheet(wb, model_spec, params)


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
    params = factors.copy()

    # Adjust number of devices to account for production yield
    params["num_1yoec"] = (
        params["num_1yoec"] / (params["coral_yield_1YOEC"] * 100) * 100
    )

    return evaluate_spreadsheet(wb, factor_spec, params)


def load_config():
    """
    Load configuration file for model sampling

    Parameters
    ----------
    config_filepath : str
        String specifying filepath of config file, default is the default package config file
    """
    prod = pd.read_csv(f"{THIS_DIR}/{DEFAULT_PROD_VER}_prod_config.csv")
    deploy = pd.read_csv(f"{THIS_DIR}/{DEFAULT_DEPLOY_VER}_deploy_config.csv")

    return pd.concat([prod, deploy], ignore_index=True)


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
# "discrete" is a convenience label in the config meaning uniform over discrete values;
# it is mapped to "unif" before being passed to SALib.
_UNIFORM_LIKE_DISTS = {"unif", "logunif", "discrete"}


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
    if (cost_type != "production") & (cost_type != "deployment"):
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

    # Map "discrete" → "unif" for SALib (SALib has no "discrete" distribution type)
    salib_dists = raw_dists.replace("discrete", "unif").to_list()

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


def _run_cost_model(wb, cost_factors, factor_spec, calculate_cost):
    """
    Run and collect results from a cost model.

    Parameters
    ----------
    wb_file_path : str
        Filepath to a cost model as an excel workbook
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
    total_cost = np.zeros((cost_factors.shape[0], 2))
    for idx_n in range(len(total_cost)):
        total_cost[idx_n, :] = calculate_cost(
            wb, factor_spec, cost_factors.iloc[idx_n, :]
        )

    try:
        cost_factors.loc[:, ["capex", "opex"]] = total_cost
    except TypeError:
        raise TypeError(
            "Incorrect type encountered. Ensure continuous values are not integers in config files."
        )

    return cost_factors


def collect_production_costs(wb, cost_factors, factor_spec):
    """
    Run the production cost model.

    Parameters
    ----------
    wb_file_path : Workbook file path
        A cost model as an excel workbook
    cost_factors : dataframe
        Dataframe of factors to input in the cost model
    factor_spec : dataframe
        Factor specification, as loaded from the config.csv

    Returns
    -------
    cost_factors : dataframe
        Updated sampled factor dataframe with costs added
    """
    return _run_cost_model(wb, cost_factors, factor_spec, calculate_production_cost)


def collect_deployment_costs(wb, cost_factors, factor_spec):
    """
    Run the deployment cost model.

    Parameters
    ----------
    wb_file_path : str
        Filepath to a cost model as an excel workbook
    cost_factors : dataframe
        Dataframe of factors to input in the cost model
    factor_spec : dataframe
        Factor specification, as loaded from the config.csv

    Returns
    -------
    cost_factors : dataframe
        Updated sampled factor dataframe with costs added
    """

    return _run_cost_model(wb, cost_factors, factor_spec, calculate_deployment_cost)


def run_deployment_model(cost_model: str, N: int):
    """
    Generate Sobol' samples for the deployment model and run

    Parameters
    ----------
    cost_model : str
        Path to cost (spreadsheet) model
    N : int
        Number of desired Sobol' sample points (resolves to `N * (2D + 2)` samples)
        where `D` is the number of model factors

    Returns
    -------
    SALib ProblemSpec with `cost_model_results` added as a field.
    """
    sp, model_config = problem_spec("deployment")
    sample_config = model_config.loc[~model_config.factor_names.isin(["capex", "opex"])]

    # Create Sobol' sample
    sp.sample_sobol(N, calc_second_order=True)

    samples = pd.DataFrame(data=sp.samples, columns=sp["names"])
    samples = convert_factor_types(samples, sample_config.is_cat)

    xlapp, wb = open_excel(cost_model)
    sample_w_cost_results = collect_deployment_costs(wb, samples, model_config)
    close_excel(xlapp, wb)

    sp["cost_model_results"] = sample_w_cost_results

    return sp


def run_production_model(cost_model: str, N: int, nprocs=1):
    """
    Generate Sobol' samples for the production model and run

    Parameters
    ----------
    cost_model : str
        Path to cost (spreadsheet) model, including extension (.xlsx)
    N : int
        Number of desired Sobol' sample points (resolves to `N * (2D + 2)` samples)
        where `D` is the number of model factors

    Returns
    -------
    SALib ProblemSpec with `cost_model_results` added as a field.
    """
    sp, model_config = problem_spec("production")
    sample_config = model_config.loc[~model_config.factor_names.isin(["capex", "opex"])]

    # Create Sobol' sample
    sp.sample_sobol(N, calc_second_order=True)

    samples = pd.DataFrame(data=sp.samples, columns=sp["names"])
    samples = convert_factor_types(samples, sample_config.is_cat)

    xlapp, wb = open_excel(cost_model)
    sample_w_cost_results = collect_production_costs(wb, samples, model_config)
    close_excel(xlapp, wb)

    sp["cost_model_results"] = sample_w_cost_results

    return sp


def extract_sa_results(sp: ProblemSpec, fig_path: str = "./figs/"):
    os.makedirs(fig_path, exist_ok=True)

    factor_names = sp["names"]
    cost_results = sp["cost_model_results"]

    # First get sensitivity to setup cost
    sp.set_samples(np.array(cost_results[factor_names]))
    sp.set_results(np.array(cost_results["capex"]))
    sp.analyze_sobol()

    axes = sp.plot()
    axes[0].set_yscale("log")
    fig = plt.gcf()  # get current figure
    fig.set_size_inches(10, 4)
    plt.tight_layout()
    plt.savefig(path_join(fig_path, "setup_cost_sobol_SA.png"))
    plt.close()

    sp.analyze_pawn()
    axes = sp.plot()
    fig = plt.gcf()  # get current figure
    fig.set_size_inches(10, 4)
    plt.tight_layout()
    plt.savefig(path_join(fig_path, "setup_cost_pawn_barplot_SA.png"))
    plt.close()

    # SALib.analyze.rsa.analyze(problem_dict, sp.samples, total_cost)
    sp.heatmap()
    fig = plt.gcf()  # get current figure
    fig.set_size_inches(10, 4)
    plt.savefig(path_join(fig_path, "setup_cost_pawn_heatmap_SA.png"))
    plt.close()

    # Then get sensitivity to operational cost
    sp.set_samples(np.array(cost_results[factor_names]))

    # Get sensitivity to operational cost
    sp.set_results(np.array(cost_results["opex"]))
    sp.analyze_sobol()

    axes = sp.plot()
    axes[0].set_yscale("log")
    fig = plt.gcf()  # get current figure
    fig.set_size_inches(10, 4)
    plt.tight_layout()
    plt.savefig(path_join(fig_path, "operational_cost_sobol_SA.png"))
    plt.close()

    sp.analyze_pawn()
    axes = sp.plot()
    fig = plt.gcf()  # get current figure
    fig.set_size_inches(10, 4)
    plt.tight_layout()
    plt.savefig(path_join(fig_path, "operational_cost_pawn_barplot_SA.png"))
    plt.close()

    sp.heatmap()
    fig = plt.gcf()
    fig.set_size_inches(10, 4)
    plt.savefig(path_join(fig_path, "operational_cost_pawn_heatmap_SA.png"))
    plt.close()
