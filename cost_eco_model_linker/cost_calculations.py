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
    apply_discrete_mapping,
    collect_deployment_costs,
    collect_production_costs,
)

from .handlers import (
    open_excel,
    close_excel,
    reset_workbook,
    create_eia_template,
    fill_EIA_info,
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
        Dataframe containing 'capex' and 'opex'
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


def initialize_cost_df(years, nsims):
    """
    Initialize dataframe for storing sampled cost data.

    Components:
    - 1 : CAPEX, sum of production and deployment cost
    - 2 : Contingency CAPEX, % of CAPEX
    - 3 : OPEX, sum of production and deployment cost
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

    sp_dep, factor_specs_dep = problem_spec("deployment")
    sp_prod, factor_specs_prod = problem_spec("production")

    specs_prod = factor_specs_prod.loc[
        ~factor_specs_prod.factor_names.isin(["capex", "opex"])
    ]
    specs_dep = factor_specs_dep.loc[
        ~factor_specs_dep.factor_names.isin(["capex", "opex"])
    ]

    # Sample production model factors
    sp_prod.sample_sobol(nsims, calc_second_order=True, skip_values=2**nsims)
    factors_df_prod = pd.DataFrame(
        data=sp_prod.samples, columns=specs_prod.factor_names
    )

    # Sample deployment model factors
    nfactors = np.min([specs_dep.shape[0], specs_prod.shape[0]]) - 2
    N, K = get_NK(nsims, nfactors)

    sp_dep.sample_sobol(N, calc_second_order=True, skip_values=2**N)
    factors_df_dep = pd.DataFrame(data=sp_dep.samples, columns=specs_dep.factor_names)

    # Ensure float type
    # factors_df_dep["capex"] = factors_df_dep.capex.astype(float)
    # factors_df_dep["opex"] = factors_df_dep.opex.astype(float)
    # factors_df_prod["capex"] = factors_df_prod.capex.astype(float)
    # factors_df_prod["opex"] = factors_df_prod.opex.astype(float)

    # Subset to just the number of sims as the scenarios beyond `nsims` do not get used
    # Yes, this means the Sobol' sampling is not necessary.
    # Based on conversation with R. Crocker, this was simply to get something working
    # reusing existing code.
    factors_df_prod = factors_df_prod.iloc[0:nsims, :]
    factors_df_dep = factors_df_dep.iloc[0:nsims, :]

    # Convert factor types to suitable format for cost model sampling
    factors_df_dep = convert_factor_types(factors_df_dep, specs_dep.is_cat)
    factors_df_prod = convert_factor_types(factors_df_prod, specs_prod.is_cat)

    factors_df_dep = apply_discrete_mapping(factors_df_dep, factor_specs_dep)
    factors_df_prod = apply_discrete_mapping(factors_df_prod, factor_specs_prod)

    return (
        factor_specs_dep,
        factors_df_dep,
        factor_specs_prod,
        factors_df_prod,
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
    # Sum over reefsets for the same intervention and year to give total number of corals
    # outplanted in each environmental sample (rep)
    temp_id_df = (
        iv_spec[["rep", "number_of_1YO_corals"]]
        .groupby("rep")["number_of_1YO_corals"]
        .sum()
        .reset_index()
    )

    # Note: Not sure why this implementation is only selecting 0 to nsims - 1
    sel = slice(0, nsims - 1)

    # Determine number of devices considering yield
    n_1yo_corals = temp_id_df["number_of_1YO_corals"].values[ecol_idx]
    yield_1yo = deploy_factors.loc[sel, "coral_yield_1YOEC"]
    n_devices = np.ceil(n_1yo_corals / yield_1yo)

    # Update 1YO corals and convert to equivalent number of devices
    deploy_factors.loc[sel, "num_1yoec"] = n_devices
    prod_factors.loc[sel, "num_1yoec"] = n_devices

    # Update number of species
    prod_factors.loc[:, "species_no"] = iv_spec["number_of_groups"].iloc[0]

    # Make sure the production and deployment models have the same 1YO coral yield per
    # device
    prod_factors.loc[:, "coral_yield_1YOEC"] = deploy_factors[
        "coral_yield_1YOEC"
    ].values

    # Use distance override
    # TODO: Have to set nearest representative reef too to get estimated haulage costs
    deploy_factors.loc[:, "distance_from_port"] = iv_spec["distance_to_port_NM"].iloc[0]

    # departure_port = deploy_ws.Range("D26").Value
    # deploy_factors.loc[:, ""]

    return deploy_factors, prod_factors


def calc_production_requirement(deploy_factors, prod_factors, iv_spec, ecol_idx, nsims):
    """
    Determine the number of devices to be produced and deployed in the years after the
    first intervention year. Setup costs should only be accrued for additional corals
    deployed relative to the previous year.

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
    # Sum over reefsets for the same intervention and year to give total number of corals
    # outplanted in each environmental sample (rep)
    temp_id_df = (
        iv_spec[["rep", "number_of_1YO_corals"]]
        .groupby("rep")["number_of_1YO_corals"]
        .sum()
        .reset_index()
    )

    # Note: Not sure why this implementation is only selecting 0 to nsims - 1
    # Ans:  It is because Sobol' samples are taken when they are not necessary
    #       which generates a larger number of scenarios than `nsims`.
    #       We are only concerned with `nsims` scenarios. The dataframe has been adjusted
    #       so it should only be of size `nsims` but we leave this here as is to avoid
    #       breaking anything just in case.
    sel = slice(0, nsims - 1)
    n_1yo_corals = temp_id_df["number_of_1YO_corals"].values[ecol_idx]
    yield_1yo_corals = deploy_factors.loc[sel, "coral_yield_1YOEC"]

    # Account for losses and inefficiencies to determine how many coral devices are needed
    # to meet production targets
    required_production = np.ceil(n_1yo_corals / yield_1yo_corals)
    if np.all(required_production == 0.0):
        return deploy_factors, prod_factors

    # Calculate total number of devices to be produced/deployed
    base_production = prod_factors.loc[sel, "num_1yoec"]
    total_prod = (required_production - base_production) + base_production

    prod_factors.loc[sel, "num_1yoec"] = total_prod
    deploy_factors.loc[sel, "num_1yoec"] = total_prod

    return deploy_factors, prod_factors


def calculate_costs(
    stores: OutputStores,
    ID_key_fn: str,
    nsims: int,
    deploy_model_filepath: str,
    prod_model_filepath: str,
    cont_p: float = 0.25,
    p_iter_id: int = 0,
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
    p_iter_id : int
        ID used for parallel sampling to keep track of batches for ordered recombination.
    """
    iv_keys_dir = stores.intervention_keys_dir
    cost_dir = stores.cost_dir

    iv_ID_key = f"ID_key_{ID_key_fn}"
    rep_idx_key = f"rep_idx_{ID_key_fn}"
    _iter_id = str(p_iter_id)
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

    deploy_xlapp, deploy_wb = open_excel(deploy_model_fp)
    prod_xlapp, prod_wb = open_excel(prod_model_fp)
    try:
        eia_template = create_eia_template(deploy_wb)

        for id_idx, scen_id in enumerate(unique_ids):
            # Intervention scenario ID to link costs to ecological model outcomes
            scen_idx = ID_key.ID == scen_id
            iv_years = np.unique(
                ID_key.intervention_years[scen_idx]
            )  # Intervention years

            # Ecological rep sampling indices
            # (`min()` because the indices should be relative to the vector selected
            # for the intervention id)
            ecol_ids = ecol_ids_df[str(scen_id)] - min(ecol_ids_df[str(scen_id)])

            cost_df = initialize_cost_df(iv_years, nsims)

            deploy_spec, deploy_factors, prod_spec, prod_factors = sample_cost_model(
                nsims
            )
            base_production_volume = deploy_factors.num_1yoec

            for iv_yr in iv_years:
                curr_selector = (ID_key.intervention_years == iv_yr) & scen_idx

                # Add key intervention parameters for year to dataframe as constants
                deploy_factors, prod_factors = update_factors(
                    deploy_factors,
                    prod_factors,
                    ID_key.loc[
                        curr_selector,
                        [
                            "number_of_1YO_corals",
                            "distance_to_port_NM",
                            "number_of_groups",
                            "rep",
                        ],
                    ],
                    ecol_ids,
                    nsims,
                )
                deploy_factors = collect_deployment_costs(
                    deploy_wb, deploy_factors, deploy_spec
                )
                prod_factors = collect_production_costs(
                    prod_wb, prod_factors, prod_spec
                )

                prev_selector = (ID_key.intervention_years == iv_yr - 1) & scen_idx
                if iv_yr > min(iv_years):
                    # Adjust setup costs to account for CAPEX that does not need to be spent
                    # again this year, superficial example: no need to buy a truck every year,
                    # just use the one from last year again.
                    deploy_factors, prod_factors = calc_production_requirement(
                        deploy_factors,
                        prod_factors,
                        ID_key.loc[prev_selector, ["number_of_1YO_corals", "rep"]],
                        ecol_ids,
                        nsims,
                    )

                    additional = (
                        deploy_factors["num_1yoec"].values[0:nsims]
                        - base_production_volume
                    )
                    no_additional = additional <= 0
                    if no_additional.any():
                        # If deploying no more than previous year, setup cost is zero
                        prod_factors.loc[no_additional, "capex"] = 0.0
                        deploy_factors.loc[no_additional, "capex"] = 0.0
                    else:
                        # If deploying more than last year, recalculate setup cost for only
                        # those additional corals
                        deploy_wb = reset_workbook(
                            deploy_xlapp, deploy_wb, deploy_model_fp
                        )
                        prod_wb = reset_workbook(prod_xlapp, prod_wb, prod_model_fp)

                        with_additional = ~no_additional

                        updated_dep_cost = collect_deployment_costs(
                            deploy_wb,
                            deploy_factors.loc[with_additional, :],
                            deploy_spec,
                        )

                        updated_prod_cost = collect_production_costs(
                            prod_wb,
                            prod_factors.loc[with_additional, :],
                            prod_spec,
                        )

                        # Replace orginally calculated setup costs with updated setup costs
                        prod_factors.loc[with_additional, "capex"] = updated_prod_cost[
                            "capex"
                        ]
                        deploy_factors.loc[with_additional, "capex"] = updated_dep_cost[
                            "capex"
                        ]

                    # Retain originally sampled operational cost for full number of corals,
                    # regardless of intervention year
                    # NOTE: No idea why
                    # prod_factors.loc[:, "cost"] = save_cost_prod
                    # deploy_factors.loc[:, "cost"] = save_cost_dep

                # Calculate all cost codes and add to dataframe
                cost_sum = (
                    deploy_factors[["capex", "opex"]] + prod_factors[["capex", "opex"]]
                ).values[0:nsims, :]
                cost_df.loc[cost_df.year == iv_yr, cost_df.columns[2:]] = cost_types(
                    cost_sum, cont_p, nsims
                )

                # Get associated port
                # deploy_ws = deploy_wb.Sheets("Logistics")
                # departure_port = deploy_ws.Range("D26").Value

                departure_port = ID_key.loc[curr_selector.idxmax(), "port_name"]
                deploy_distance = ID_key.loc[
                    curr_selector.idxmax(), "distance_to_port_NM"
                ]

                eia_template = fill_EIA_info(
                    prod_wb,
                    deploy_wb,
                    scen_id,
                    min(iv_years),
                    iv_yr,
                    deploy_distance,
                    departure_port,
                    eia_template,
                )

                deploy_wb = reset_workbook(deploy_xlapp, deploy_wb, deploy_model_fp)
                prod_wb = reset_workbook(prod_xlapp, prod_wb, prod_model_fp)

            # Write cost results to file
            cost_filepath = path_join(
                cost_dir,
                f"ID{scen_id}intervention_mc_cost_data_iter_id{p_iter_id}.csv",
            )

            cost_df.to_csv(cost_filepath, index=False)
            cost_filepaths[id_idx] = cost_filepath

        eia_template.to_csv(path_join(cost_dir, f"id_{iv_ID_key}_EIA.csv"))
    finally:
        close_excel(deploy_xlapp, deploy_wb)
        close_excel(prod_xlapp, prod_wb)

    return cost_filepaths
