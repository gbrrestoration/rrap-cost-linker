import os
from os.path import join as path_join
from win32com import client as w32client
from SALib import ProblemSpec
import numpy as np
import pandas as pd

import matplotlib.pyplot as plt

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_VER = "3.8.0"


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
        Cost: float
            Operational cost
        setupCost: float
            Setup cost
    """
    reef_key = ["Moore", "Davies", "Swains", "Keppel"]
    port = factors["port"].iloc[0]
    factor_names = model_spec.factor_names

    is_not_cost = factor_names != "Cost"
    is_not_setup = factor_names != "setupCost"
    for _, params in model_spec[is_not_cost & is_not_setup].iterrows():
        param_names = params.factor_names
        ws = wb.Sheets(params.sheet)
        if param_names == "distance_from_port":
            ws.Range(params.cell_pos).Value = factors[param_names].iloc[0]
        elif param_names == "port":
            ws.Range(params.cell_pos).Value = reef_key[port - 1]
        else:
            ws.Range(params.cell_pos).Value = factors[param_names].iloc[0]

    ws = wb.Sheets("Dashboard")
    ws.EnableCalculation = True
    ws.Calculate()

    # Get the new output
    cost_cell = model_spec.loc[factor_names == "Cost", "cell_pos"].values[0]
    setupcost_cell = model_spec.loc[factor_names == "setupCost", "cell_pos"].values[0]

    Cost = ws.Range(cost_cell).Value
    setupCost = ws.Range(setupcost_cell).Value

    return [Cost, setupCost]


def calculate_production_cost(wb, factor_spec, factors):
    """
    Calculates set up and operational costs in the production cost model (wb), given a set of parameters to sample.

    Parameters
    ----------
    wb : Workbook
        The cost model as an excel workbook
    factor_spec : dataframe
        factor specification, as loaded from the config.csv
    factors : dataframerow
        Row of a pandas dataframe with factors to sample

    Returns
    -------
    Cost: float
        Operational cost
    setupCost: float
        Setup cost
    """
    factor_names = factor_spec.factor_names
    not_costs = (factor_names != "Cost") & (factor_names != "setupCost")
    for _, factor_row in factor_spec[not_costs].iterrows():
        ws = wb.Sheets(factor_row.sheet)
        ws.Range(factor_row.cell_pos).Value = factors[factor_row.factor_names].iloc[0]

    ws = wb.Sheets("Dashboard")
    ws.EnableCalculation = True
    ws.Calculate()

    # get the new output
    cost_cells = factor_spec.loc[factor_names == "Cost", "cell_pos"].values[0]
    setupcost_cells = factor_spec.loc[factor_names == "setupCost", "cell_pos"].values[0]

    Cost = ws.Range(cost_cells).Value
    setupCost = ws.Range(setupcost_cells).Value

    return [Cost, setupCost]


def load_config():
    """
    Load configuration file for model sampling

    Parameters
    ----------
    config_filepath : str
        String specifying filepath of config file, default is the default package config file
    """
    prod = pd.read_csv(f"{THIS_DIR}/{DEFAULT_VER}_prod_config.csv")
    deploy = pd.read_csv(f"{THIS_DIR}/{DEFAULT_VER}_deploy_config.csv")

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
    model_spec = model_spec[model_spec.cost_type == cost_type]
    factor_ranges = [
        model_spec[["range_lower", "range_upper"]].iloc[k].values
        for k in range(model_spec.shape[0])
    ]

    problem_dict = {
        "num_vars": model_spec.shape[0],
        "names": [name for name in model_spec.factor_names],
        "bounds": factor_ranges,
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
            factors_df[factors_df.columns[ic_ind]] = np.ceil(
                factors_df[factors_df.columns[ic_ind]]
            ).astype(int)

    return factors_df


def _run_cost_model(wb_file_path, cost_factors, factor_spec, calculate_cost):
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
        Function to use to sample cost

    Returns
    -------
    cost_factors : dataframe
        Updated dataframe with costs added
    """
    # win32com Excel interface can only open files using their absolute paths
    wb_file_path = os.path.abspath(wb_file_path)

    # Open workbook
    xlapp = w32client.DispatchEx("Excel.Application")
    xlapp.Interactive = False
    xlapp.Visible = False
    xlapp.DisplayAlerts = False
    wb = xlapp.Workbooks.Open(wb_file_path)

    total_cost = np.zeros((cost_factors.shape[0], 2))
    for idx_n in range(len(total_cost)):
        total_cost[idx_n, :] = calculate_cost(
            wb, factor_spec, cost_factors.iloc[[idx_n]]
        )

    cost_factors.loc[:, "Cost"] = total_cost[:, 0]
    cost_factors.loc[:, "setupCost"] = total_cost[:, 1]

    wb.Close(SaveChanges=False)  # Close workbook
    xlapp.Quit()
    return cost_factors


def collect_deployment_costs(wb_file_path, cost_factors, factor_spec):
    """
    Run the production cost model.

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
    return _run_cost_model(
        wb_file_path, cost_factors, factor_spec, calculate_deployment_cost
    )


def collect_production_costs(wb_file_path, cost_factors, factor_spec):
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
    return _run_cost_model(
        wb_file_path, cost_factors, factor_spec, calculate_production_cost
    )


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

    # Create Sobol' sample
    sp.sample_sobol(N, calc_second_order=True)

    samples = pd.DataFrame(data=sp.samples, columns=sp["names"])

    samples = convert_factor_types(samples, model_config.is_cat)

    sample_w_cost_results = collect_deployment_costs(cost_model, samples, model_config)

    sp["cost_model_results"] = sample_w_cost_results

    return sp


def run_production_model(cost_model: str, N: int):
    """
    Generate Sobol' samples for the production model and run

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
    sp, model_config = problem_spec("production")

    # Create Sobol' sample
    sp.sample_sobol(N, calc_second_order=True)

    samples = pd.DataFrame(data=sp.samples, columns=sp["names"])

    samples = convert_factor_types(samples, model_config.is_cat)

    sample_w_cost_results = collect_production_costs(cost_model, samples, model_config)

    sp["cost_model_results"] = sample_w_cost_results

    return sp


def extract_sa_results(sp: ProblemSpec, fig_path: str = "./figs/"):
    os.makedirs(fig_path, exist_ok=True)

    factor_names = sp["names"]
    cost_results = sp["cost_model_results"]

    # First get sensitivity to setup cost
    sp.set_results(np.array(cost_results["setupCost"]))
    sp.analyze_sobol()

    sp.samples = np.array(cost_results[factor_names])

    sp.set_results(np.array(cost_results["setupCost"]))
    sp.analyze_sobol()

    axes = sp.plot()
    axes[0].set_yscale("log")
    fig = plt.gcf()  # get current figure
    fig.set_size_inches(10, 4)
    plt.tight_layout()

    plt.savefig(path_join(fig_path, "setup_cost_sobol_SA.png"))

    sp.analyze_pawn()
    axes = sp.plot()
    fig = plt.gcf()  # get current figure
    fig.set_size_inches(10, 4)
    plt.tight_layout()
    plt.savefig(path_join(fig_path, "setup_cost_pawn_barplot_SA.png"))

    # SALib.analyze.rsa.analyze(problem_dict, sp.samples, total_cost)
    sp.heatmap()
    fig = plt.gcf()  # get current figure
    fig.set_size_inches(10, 4)
    plt.savefig(path_join(fig_path, "setup_cost_pawn_heatmap_SA.png"))

    # Then get sensitivity to operational cost
    sp.set_samples(np.array(cost_results[factor_names]))

    # Get sensitivity to operational cost
    sp.set_results(np.array(cost_results["Cost"]))
    sp.analyze_sobol()

    axes = sp.plot()
    axes[0].set_yscale("log")
    fig = plt.gcf()  # get current figure
    fig.set_size_inches(10, 4)
    plt.tight_layout()
    plt.savefig(path_join(fig_path, "operational_cost_sobol_SA.png"))

    sp.analyze_pawn()
    axes = sp.plot()
    fig = plt.gcf()  # get current figure
    fig.set_size_inches(10, 4)
    plt.tight_layout()
    plt.savefig(path_join(fig_path, "operational_cost_pawn_barplot_SA.png"))

    sp.heatmap()
    fig.set_size_inches(10, 4)
    plt.savefig(path_join(fig_path, "operational_cost_pawn_heatmap_SA.png"))
