import os
from os.path import join as path_join

import shutil
import tempfile

import numpy as np
import pandas as pd

from .setup_results import OutputStores
from .sampling import (
    problem_spec,
    convert_factor_types,
    collect_deployment_costs,
    collect_production_costs,
)

THIS_DIR = os.path.dirname(__file__)


def get_NK(nsims, n_factors):
    """
    Calculate number of input Sobol samples, N, given number of total simulations required and number of factors.
    Want an output number of samples, N*K , as close to the required number of sims as possible, where
    K = (2*n_factors + 2).
    See https://salib.readthedocs.io/en/latest/api.html#sobol-sensitivity-analysis
    """
    K = int((2 * n_factors) + 2)

    return int(np.ceil(nsims / K)), K


def cost_types(cost, contingency, nsims):
    """
    Calculate key cost codes:
    - 1 : CAPEX,  sum of production and deployment cost
    - 2 : Contingency CAPEX,  % of CAPEX
    - 3 : OPEX,  sum of production and deployment cost
    - 4 : Sustaining capital OPEX, set to zero for now (assumed to be included in OPEX through contract)
    - 5 : Contingency OPEX, % of OPEX
    - 6 : Vessel fuel, only relevant if volunteer vessels are used - set to zero for now
    - 7 : CAPEX-monitoring, set to zero (assumed no monitoring cost)
    - 8 : Contingency CAPEX-monitoring, % of CAPEX-monitoring
    - 9 : OPEX-monitoring, set to zero (assumed no monitoring cost)
    - 10 : Sustaining capital OPEX-monitoring, set to zero (assumed no monitoring cost)
    - 11 : Contingency OPEX-monitoring, % of OPEX-monitoring

    Parameters
    ----------
    cost : dataframe
        Dataframe containing 'Cost' and 'setupCost'
    contingency : float
        Contingency proportion.
    nsims : int
        Total number of simulations (from metrics sampling)
    """
    return np.vstack(
        (
            np.vstack(
                (
                    cost[:, 0],
                    cost[:, 0] * contingency,
                    cost[:, 1],
                    np.zeros(nsims),
                    cost[:, 1] * contingency,
                )
            ),
            np.zeros((6, nsims)),
        )
    )


def initialise_cost_df(years, nsims):
    """
    Initialize dataframe for storing sampled cost data.

    Parameters
    ----------
    years : np.array
        Intervention years
    nsims : int
        Total number of simulations (from metrics sampling)

    Returns
    -------
    cost_df : dataframe
    """
    # Dataframe for saving cost data to
    n_years = len(years)
    cols = ["year", "component"] + ["draw" + str(n) for n in range(1, nsims + 1)]
    cost_df = pd.DataFrame(np.zeros((n_years * 11, 2 + nsims)), columns=cols)
    cost_df.loc[:, "year"] = np.array(np.repeat(years, 11))
    cost_df.loc[:, "component"] = np.tile(np.array(range(1, 12)), n_years)

    return cost_df


def sample_cost_model(nsims):
    """
    Sample cost model parameters.

    Parameters
    ----------
    nsims : int
        Total number of simulations (from metrics sampling)

    Returns
    -------
    factor_specs_dep : dict
        Factor specification for sampling factors in the deployment cost model.
    factors_df_dep : dataframe
        Sampled factors for the deployment cost model.
    factor_specs_prod : dict
        Factor specification for sampling factors in the production cost model.
    factors_df_prod : dataframe
        Sampled factors for the production cost model
    """
    # Sample deployment model factors
    sp_dep, factor_specs_dep = problem_spec("deployment")
    sp_prod, factor_specs_prod = problem_spec("production")

    nfactors = np.min([factor_specs_dep.shape[0], factor_specs_prod.shape[0]]) - 2
    N, K = get_NK(nsims, nfactors)

    sp_dep.sample_sobol(N, calc_second_order=True, skip_values=2**N)
    factors_df_dep = pd.DataFrame(
        data=sp_dep.samples, columns=factor_specs_dep.factor_names
    )

    # Sample production model factors
    sp_prod.sample_sobol(N, calc_second_order=True, skip_values=2**N)
    factors_df_prod = pd.DataFrame(
        data=sp_prod.samples, columns=factor_specs_prod.factor_names
    )

    # Convert factor types to suitable format for cost model sampling
    factors_df_dep = convert_factor_types(factors_df_dep, factor_specs_dep.is_cat)
    factors_df_prod = convert_factor_types(factors_df_prod, factor_specs_prod.is_cat)

    return (
        factor_specs_dep,
        factors_df_dep.iloc[0 : N * K],
        factor_specs_prod,
        factors_df_prod.iloc[0 : N * K],
    )


def update_factors(deploy_factors, prod_factors, iv_spec, ecol_idx, nsims):
    """
    Update sampled cost model parameter dataframes with intervention specific parameters.

    Parameters
    ----------
    deploy_factors : dataframe
        Factors dataframe for the deployment cost model.
    prod_factors : dataframe
        Factors dataframe for the production cost model
    iv_spec : dataframe
        Intervention specification dataframe containing intervention parameters.
    ecol_idx : int
        Indices mapping scenario IDs in the RME results to samples in nsims.
    nsims : int
        Number of simulations drawn (may be smaller than dataframe size to get correct number of samples
        for Sobol Sampling).
    """
    # Sum over reefsets for the same intervention and year to give total number of corals outplanted in each environmental sample (rep)
    temp_id_df = (
        iv_spec[["rep", "number_of_1YO_corals"]]
        .groupby("rep")["number_of_1YO_corals"]
        .sum()
        .reset_index()
    )

    # Update 1YO corals and convert to equivalent number of devices
    deploy_factors.loc[0 : nsims - 1, "num_devices"] = np.ceil(
        temp_id_df["number_of_1YO_corals"].values[ecol_idx]
        / deploy_factors.loc[0 : nsims - 1, "1YOEC_yield"]
    )
    prod_factors.loc[0 : nsims - 1, "num_devices"] = np.ceil(
        temp_id_df["number_of_1YO_corals"].values[ecol_idx]
        / deploy_factors.loc[0 : nsims - 1, "1YOEC_yield"]
    )

    # Update number of species
    prod_factors.loc[:, "species_no"] = iv_spec["number_of_species"].iloc[0]

    # Make sure the production and deployment models have the same 1YO coral yield per device
    prod_factors.loc[:, "1YOEC_yield"] = deploy_factors["1YOEC_yield"].values

    # Port does not matter as we are using distance to port directly
    deploy_factors.loc[:, "port"] = 1
    deploy_factors.loc[:, "distance_from_port"] = iv_spec["distance_to_port_NM"].iloc[0]

    return deploy_factors, prod_factors


def calc_setup_costs(deploy_factors, prod_factors, iv_spec, ecol_idx, nsims):
    """
    Update number of corals to correctly calculate setup cost for years after the first
    intervention year. Setup costs are only accrued for additional corals deployed relative
    to the previous year.

    Parameters
    ----------
    deploy_factors : dataframe
        Factors dataframe for the deployment cost model.
    prod_factors : dataframe
        Factors dataframe for the production cost model
    iv_spec : dataframe
        Intervention specification dataframe containing intervention parameters.
    ecol_idx : int
        Indices mapping scenario IDs in the RME results to samples in nsims.
    nsims : int
        Number of simulations drawn (may be smaller than dataframe size to get correct number of samples
        for Sobol Sampling).
    """
    # Sum over reefsets for the same intervention and year to give total number of corals outplanted in each environmental sample (rep)
    temp_id_df = (
        iv_spec[["rep", "number_of_1YO_corals"]]
        .groupby("rep")["number_of_1YO_corals"]
        .sum()
        .reset_index()
    )

    # Update 1YO corals ro additional 1YO corals compared to previous year and convert to equivalent number of devices
    deploy_factors.loc[0 : nsims - 1, "num_devices"] = deploy_factors.loc[
        0 : nsims - 1, "num_devices"
    ] - np.ceil(
        temp_id_df["number_of_1YO_corals"].values[ecol_idx]
        / deploy_factors.loc[0 : nsims - 1, "1YOEC_yield"]
    )
    prod_factors.loc[0 : nsims - 1, "num_devices"] = prod_factors.loc[
        0 : nsims - 1, "num_devices"
    ] - np.ceil(
        temp_id_df["number_of_1YO_corals"].values[ecol_idx]
        / deploy_factors.loc[0 : nsims - 1, "1YOEC_yield"]
    )

    return deploy_factors, prod_factors


def calculate_costs(
    stores: OutputStores,
    ID_key_fn: str,
    nsims: int,
    deploy_model_filepath: str,
    prod_model_filepath: str,
    cont_p: float = 0.25,
    iter_id: int = 0,
):
    """
    Sample costs for a set of interventions specified in ID_key, sampling nsims.

    Parameters
    ----------
    stores : OutputStores
        Data class holding output directory locations
    ID_key_fn : str
        Target filename for output.
    nsims : int
        Total number of draws to sample cost models, should match ecological metrics sampling.
    deploy_model_filepath : string
        Path to deployment cost model.
    prod_model_filepath : string
        Path to production cost model.
    cont_p : float
        Contingency cost proportion.
    iter_id : int
        ID used for parallel sampling to keep track of batches for ordered recombination.
    """
    iv_keys_dir = stores.intervention_keys_dir
    cost_dir = stores.cost_dir

    iv_ID_key = f"ID_key_{ID_key_fn}"
    rep_idx_key = f"rep_idx_{ID_key_fn}"
    _iter_id = str(iter_id)
    run_id = f"run{_iter_id}"

    ID_key = pd.read_csv(
        path_join(iv_keys_dir, f"intervention_{iv_ID_key}_{run_id}.csv")
    )
    ecol_ids_df = pd.read_csv(
        path_join(iv_keys_dir, f"intervention_{rep_idx_key}_{run_id}.csv")
    )

    tmp_dir = tempfile.mkdtemp(prefix="ceml_")

    # Copy files for independent run
    deploy_model_fp = path_join(tmp_dir, f"{deploy_model_filepath}{_iter_id}.xlsx")
    os.makedirs(os.path.dirname(deploy_model_fp), exist_ok=True)
    shutil.copy(deploy_model_filepath + ".xlsx", deploy_model_fp)

    prod_model_fp = path_join(tmp_dir, f"{prod_model_filepath}{_iter_id}.xlsx")
    os.makedirs(os.path.dirname(prod_model_fp), exist_ok=True)
    shutil.copy(prod_model_filepath + ".xlsx", prod_model_fp)

    unique_ids = np.unique(ID_key.ID)
    cost_filepaths = [""] * len(unique_ids)

    for id_idx, scen_id in enumerate(unique_ids):
        # Intervention scenario ID to link costs to ecological model outcomes
        scen_idx = ID_key.ID == scen_id
        int_years = np.unique(ID_key.intervention_years[scen_idx])  # Intervention years

        # Ecological rep sampling indices
        # (`min()` because the indices should be relative to the vector selected
        # for the intervention id)
        ecol_ids = ecol_ids_df[str(scen_id)] - min(ecol_ids_df[str(scen_id)])

        cost_df = initialise_cost_df(int_years, nsims)

        deploy_spec, deploy_factors, prod_spec, prod_factors = sample_cost_model(nsims)

        for int_yr in int_years:
            # Add key intervention parameters for year to dataframe as constants
            deploy_factors, prod_factors = update_factors(
                deploy_factors,
                prod_factors,
                ID_key.loc[
                    (ID_key.intervention_years == int_yr) & scen_idx,
                    [
                        "number_of_1YO_corals",
                        "distance_to_port_NM",
                        "number_of_species",
                        "rep",
                    ],
                ],
                ecol_ids,
                nsims,
            )
            deploy_factors = collect_deployment_costs(
                deploy_model_fp, deploy_factors, deploy_spec
            )
            prod_factors = collect_production_costs(
                prod_model_fp, prod_factors, prod_spec
            )

            if int_yr > min(int_years):
                # Save calculated operational costs
                save_cost_prod = prod_factors["Cost"]
                save_cost_dep = deploy_factors["Cost"]

                # Adjust number of corals to "how many more are being deployed this year
                # than last year?" to caculate setup cost correctly
                deploy_factors, prod_factors = calc_setup_costs(
                    deploy_factors,
                    prod_factors,
                    ID_key.loc[
                        (ID_key.intervention_years == int_yr - 1) & scen_idx,
                        ["number_of_1YO_corals", "rep"],
                    ],
                    ecol_ids,
                    nsims,
                )

                if any(deploy_factors["num_devices"].values[0:nsims] <= 0):
                    # If deploying no more than previous year, setup cost is zero
                    prod_factors.loc[
                        deploy_factors["num_devices"] <= 0, "setupCost"
                    ] = 0
                    deploy_factors.loc[
                        deploy_factors["num_devices"] <= 0, "setupCost"
                    ] = 0

                if any(deploy_factors["num_devices"].values[0:nsims] > 0):
                    # If deploying more than last year, recalculate setup cost for only those additional corals
                    active_deployment = deploy_factors["num_devices"] > 0
                    factors_df_dep_new = collect_deployment_costs(
                        deploy_model_fp,
                        deploy_factors.loc[active_deployment, :],
                        deploy_spec,
                    )
                    factors_df_prod_new = collect_production_costs(
                        prod_model_fp,
                        prod_factors.loc[active_deployment, :],
                        prod_spec,
                    )

                    # Replace orginally calculated setup costs with updated setup costs
                    prod_factors.loc[deploy_factors["num_devices"] > 0, "setupCost"] = (
                        factors_df_prod_new["setupCost"]
                    )
                    deploy_factors.loc[
                        deploy_factors["num_devices"] > 0, "setupCost"
                    ] = factors_df_dep_new["setupCost"]

                # Retain originally sampled operational cost for full number of corals, regardless of intervention year
                prod_factors.loc[:, "Cost"] = save_cost_prod
                deploy_factors.loc[:, "Cost"] = save_cost_dep

            # Calculate all cost codes and add to dataframe
            cost_sum = (
                deploy_factors[["setupCost", "Cost"]]
                + prod_factors[["setupCost", "Cost"]]
            ).values[0:nsims, :]
            cost_df.loc[cost_df.year == int_yr, cost_df.columns[2:]] = cost_types(
                cost_sum, cont_p, nsims
            )

        cost_filepath = path_join(
            cost_dir,
            f"ID{scen_id}intervention_mc_cost_data_iter_id{iter_id}.csv",
        )

        cost_df.to_csv(cost_filepath, index=False)
        cost_filepaths[id_idx] = cost_filepath

    return cost_filepaths
