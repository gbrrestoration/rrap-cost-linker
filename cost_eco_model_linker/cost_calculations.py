import os
from os.path import join as path_join

import shutil
import tempfile

import numpy as np
import pandas as pd

from .setup_results import OutputStores
from .sampling import (
    problem_spec,
    get_NK,
    convert_factor_types,
    apply_discrete_mapping,
    collect_deployment_costs,
    collect_production_costs,
    collect_lm_costs,
    _apply_lm_inventory_model,
)

from .handlers import (
    open_excel,
    close_excel,
    reset_workbook,
    create_eia_template,
    fill_EIA_info,
    create_lm_eia_template,
    fill_lm_EIA_info,
)

THIS_DIR = os.path.dirname(__file__)


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
        All simulation years (non-intervention years will have zero costs)
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
    cost_df.loc[:, "year"] = np.array(np.repeat(years, 11)).astype(int)
    cost_df.loc[:, "component"] = np.tile(np.array(range(1, 12)), n_years).astype(int)

    return cost_df


def _fill_eia_missing_years(eia_template, all_years):
    """Add zero-cost rows for simulation years absent from the EIA template.

    For each unique (iteration, intervention, location, type) combination already
    in the template, a zero row is inserted for every year in ``all_years`` that
    has no entry, so the output covers the full simulation time series.
    """
    if eia_template.empty:
        return eia_template

    key_cols = ["iteration", "intervention", "location", "type"]
    cost_cols = [c for c in eia_template.columns if c not in key_cols + ["year"]]
    groups = eia_template[key_cols].drop_duplicates()

    new_rows = []
    for _, grp in groups.iterrows():
        mask = (eia_template[key_cols] == grp.values).all(axis=1)
        present = set(eia_template.loc[mask, "year"])
        for yr in all_years:
            if yr not in present:
                row = grp.to_dict()
                row["year"] = int(yr)
                row.update({c: 0.0 for c in cost_cols})
                new_rows.append(row)

    if new_rows:
        eia_template = pd.concat(
            [eia_template, pd.DataFrame(new_rows, columns=eia_template.columns)],
            ignore_index=True,
        )

    return eia_template


def sample_cost_model(nsims):
    """
    Sample cost model parameters for production, deployment, and LM models.

    Parameters
    ----------
    nsims : int or None
        Total number of simulations (from metrics sampling).  When ``None``
        or ``1`` Sobol' sampling is skipped and a single row of
        ``best_point_value`` entries is returned instead.

    Returns
    -------
    factor_specs_prod : DataFrame
    factors_df_prod : DataFrame
    factor_specs_dep : DataFrame
    factors_df_dep : DataFrame
    factor_specs_lm : DataFrame
    factors_df_lm : DataFrame
    """
    sp_dep, factor_specs_dep = problem_spec("deployment")
    sp_prod, factor_specs_prod = problem_spec("production")
    sp_lm, factor_specs_lm = problem_spec("lm")

    specs_prod = factor_specs_prod.loc[
        ~factor_specs_prod.factor_names.isin(["capex", "opex"])
    ]
    specs_dep = factor_specs_dep.loc[
        ~factor_specs_dep.factor_names.isin(["capex", "opex"])
    ]
    specs_lm = factor_specs_lm.loc[
        ~factor_specs_lm.factor_names.isin(["capex", "opex"])
    ]

    if nsims is None or nsims == 1:
        # Best-point / deterministic run — use best_point_value directly.
        # best_point_value is already in real-value space so no type
        # conversion or discrete mapping is required.
        factors_df_prod = pd.DataFrame(
            [dict(zip(specs_prod.factor_names, specs_prod.best_point_value))]
        )
        factors_df_dep = pd.DataFrame(
            [dict(zip(specs_dep.factor_names, specs_dep.best_point_value))]
        )
        factors_df_lm = pd.DataFrame(
            [dict(zip(specs_lm.factor_names, specs_lm.best_point_value))]
        )
    else:
        # Sample production model factors
        nfactors = np.min([specs_dep.shape[0], specs_prod.shape[0]]) - 2
        N, K = get_NK(nsims, nfactors, calc_second_order=False)
        sp_prod.sample_sobol(N, calc_second_order=False, skip_values=2**N)
        factors_df_prod = pd.DataFrame(
            data=sp_prod.samples, columns=specs_prod.factor_names
        )

        # Sample deployment model factors
        nfactors = np.min([specs_dep.shape[0], specs_prod.shape[0]]) - 2
        N, K = get_NK(nsims, nfactors, calc_second_order=False)
        sp_dep.sample_sobol(N, calc_second_order=False, skip_values=2**N)
        factors_df_dep = pd.DataFrame(
            data=sp_dep.samples, columns=specs_dep.factor_names
        )

        # Sample LM model factors
        N, K = get_NK(nsims, specs_lm.shape[0], calc_second_order=False)
        sp_lm.sample_sobol(N, calc_second_order=False, skip_values=2**N)
        factors_df_lm = pd.DataFrame(data=sp_lm.samples, columns=specs_lm.factor_names)

        # Subset to just the number of sims as the scenarios beyond `nsims` do not get used
        # Yes, this means the Sobol' sampling is not necessary.
        # Based on conversation with R. Crocker, this was simply to get something working
        # reusing existing code.
        factors_df_prod = factors_df_prod.iloc[0:nsims, :]
        factors_df_dep = factors_df_dep.iloc[0:nsims, :]
        factors_df_lm = factors_df_lm.iloc[0:nsims, :]

        # Convert factor types to suitable format for cost model sampling
        factors_df_dep = convert_factor_types(factors_df_dep, specs_dep.is_cat)
        factors_df_prod = convert_factor_types(factors_df_prod, specs_prod.is_cat)
        factors_df_lm = convert_factor_types(factors_df_lm, specs_lm.is_cat)
        factors_df_dep = apply_discrete_mapping(factors_df_dep, factor_specs_dep)
        factors_df_prod = apply_discrete_mapping(factors_df_prod, factor_specs_prod)
        factors_df_lm = apply_discrete_mapping(factors_df_lm, factor_specs_lm)

    return (
        factor_specs_prod,
        factors_df_prod,
        factor_specs_dep,
        factors_df_dep,
        factor_specs_lm,
        factors_df_lm,
    )


def lm_opex_distance_multiplier(distance_nm: float) -> float:
    """
    Return the OPEX multiplier for LM interventions based on deployment distance.

    Derived from the regression 0.2495 * x^0.517, where x is distance in
    nautical miles. The relationship is calibrated so that 15 NM → ×1.0 (100%),
    30 NM → ×1.5, 60 NM → ×2.0, 120 NM → ×3.0.

    Parameters
    ----------
    distance_nm : float
        Distance from port in nautical miles.

    Returns
    -------
    float
        Multiplier to apply to the raw LM OPEX value.
    """
    return 0.2495 * (distance_nm**0.517)


def update_lm_factors(lm_factors, iv_spec, pool_min, pool_max):
    """
    Update sampled LM factor dataframe with the year-specific larval release
    pool count derived from coral counts in the intervention specification.

    Parameters
    ----------
    lm_factors : DataFrame
        Factors dataframe for the LM cost model.
    iv_spec : DataFrame
        Intervention specification for the current rep and year (one row per
        reefset); must contain ``number_of_1YO_corals``.
    pool_min : int
        Minimum valid pool count (``range_lower`` from LM config).
    pool_max : int
        Maximum valid pool count (``range_upper`` from LM config).

    Returns
    -------
    lm_factors : DataFrame
    """
    n_corals = iv_spec["number_of_1YO_corals"].sum()
    pools = np.clip(
        np.ceil(n_corals / lm_factors["yield_per_pool"].values),
        pool_min,
        pool_max,
    ).astype(int)
    lm_factors = lm_factors.copy()
    lm_factors["larval release pools"] = pools
    return lm_factors


def update_factors(prod_factors, deploy_factors, iv_spec):
    """
    Update sampled cost model parameter dataframes with intervention specific parameters
    for a single ecological repeat.

    Parameters
    ----------
    prod_factors : dataframe
        Factors dataframe for the production cost model.
    deploy_factors : dataframe
        Factors dataframe for the deployment cost model.
    iv_spec : dataframe
        Intervention specification dataframe for the current rep and year,
        containing one row per reefset.
    """
    # Sum coral count over reefsets for this rep and year
    n_1yo_corals = iv_spec["number_of_1YO_corals"].sum()

    # Convert coral count to number of devices required to achieve the target,
    # accounting for production yield. Both models expect device counts as input.
    yield_1yo = deploy_factors["coral_yield_1YOEC"]
    n_devices = np.ceil(n_1yo_corals / yield_1yo)

    deploy_factors.loc[:, "num_1yoec"] = n_devices
    prod_factors.loc[:, "num_1yoec"] = n_devices

    # Make sure the production and deployment models have the same 1YO coral yield per device
    prod_factors.loc[:, "coral_yield_1YOEC"] = deploy_factors[
        "coral_yield_1YOEC"
    ].values

    # Use distance override
    deploy_factors.loc[:, "distance_from_port"] = iv_spec["distance_to_port_NM"].iloc[0]

    return prod_factors, deploy_factors


def calc_production_requirement(deploy_factors, prev_iv_spec):
    """
    Calculate the number of devices required in the previous intervention year for a
    single ecological repeat. Used to determine whether additional production capacity is
    needed in the current year.

    Parameters
    ----------
    deploy_factors : dataframe
        Factors dataframe for the deployment cost model (used for yield values).
    prev_iv_spec : dataframe
        Intervention specification dataframe for the previous intervention year and rep,
        containing one row per reefset.

    Returns
    -------
    prev_devices : np.ndarray
        Number of devices required in the previous intervention year, per simulation.
    """
    n_1yo_corals = prev_iv_spec["number_of_1YO_corals"].sum()
    return np.ceil(n_1yo_corals / deploy_factors["coral_yield_1YOEC"])


def calculate_costs(
    stores: OutputStores,
    ID_key_fn: str,
    nsims: int,
    deploy_model_filepath: str,
    prod_model_filepath: str,
    lm_model_filepath: str,
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
    lm_model_filepath : string
        Path to LM cost model.
    cont_p : float
        Contingency cost proportion.
    p_iter_id : int
        ID used for parallel sampling to keep track of batches for ordered recombination.
    """
    iv_keys_dir = stores.intervention_keys_dir
    cost_dir = stores.cost_dir

    iv_ID_key = f"ID_key_{ID_key_fn}"
    _iter_id = str(p_iter_id)
    run_id = f"run{_iter_id}"

    ID_key = pd.read_csv(
        path_join(iv_keys_dir, f"intervention_{iv_ID_key}_{run_id}.csv")
    )

    tmp_dir = tempfile.mkdtemp(prefix="ceml_")

    # Copy files for independent run
    deploy_model_fp = path_join(tmp_dir, f"{deploy_model_filepath}{_iter_id}.xlsx")
    os.makedirs(os.path.dirname(deploy_model_fp), exist_ok=True)
    shutil.copy(deploy_model_filepath + ".xlsx", deploy_model_fp)

    prod_model_fp = path_join(tmp_dir, f"{prod_model_filepath}{_iter_id}.xlsx")
    os.makedirs(os.path.dirname(prod_model_fp), exist_ok=True)
    shutil.copy(prod_model_filepath + ".xlsx", prod_model_fp)

    lm_model_fp = path_join(tmp_dir, f"{lm_model_filepath}{_iter_id}.xlsx")
    os.makedirs(os.path.dirname(lm_model_fp), exist_ok=True)
    shutil.copy(lm_model_filepath + ".xlsx", lm_model_fp)

    # Read pool bounds once from config so update_lm_factors can clamp each year
    from .sampling import DEFAULT_LM_VER

    _lm_cfg = pd.read_csv(os.path.join(THIS_DIR, f"{DEFAULT_LM_VER}_LM_config.csv"))
    _pool_row = _lm_cfg.loc[_lm_cfg["factor_names"] == "larval release pools"].iloc[0]
    lm_pool_min = int(_pool_row["range_lower"])
    lm_pool_max = int(_pool_row["range_upper"])

    # Full simulation year range — costs are zero for non-intervention years
    start_year = int(ID_key["start_year"].iloc[0])
    end_year = int(ID_key["end_year"].iloc[0])
    all_sim_years = np.arange(start_year, end_year + 1)

    unique_ids = np.unique(ID_key.ID)
    cost_filepaths = []

    # Open all three workbooks in a single Excel application to avoid
    # RPC_E_DISCONNECTED errors that occur when multiple DispatchEx instances
    # run simultaneously and one disconnects the others.
    xlapp, deploy_wb = open_excel(deploy_model_fp)
    _, prod_wb = open_excel(prod_model_fp, xlapp)
    _, lm_wb = open_excel(lm_model_fp, xlapp)
    try:
        for scen_id in unique_ids:
            # Output EIA asessment for each intervention scenario
            eia_template_prod = create_eia_template(prod_wb)
            eia_template_deploy = create_eia_template(deploy_wb)
            eia_template_lm = create_lm_eia_template(lm_wb)

            scen_idx = ID_key.ID == scen_id
            iv_years = np.unique(ID_key.intervention_years[scen_idx])
            unique_reps = np.unique(ID_key.rep[scen_idx])

            rep_cost_dfs = []

            for rep in unique_reps:
                rep_idx = scen_idx & (ID_key.rep == rep)

                cost_df = initialize_cost_df(all_sim_years, nsims)

                # Sample cost model parameters once per rep — fixed across years
                (
                    prod_spec,
                    prod_factors,
                    deploy_spec,
                    deploy_factors,
                    lm_spec,
                    lm_factors,
                ) = sample_cost_model(nsims)

                # Save sampled parameters so draws can be cross-checked manually
                for _label, _df in [
                    ("production", prod_factors),
                    ("deployment", deploy_factors),
                    ("lm", lm_factors),
                ]:
                    _params_fp = path_join(
                        cost_dir,
                        f"ID{scen_id}_rep{rep}_cost_params_{_label}_pid{p_iter_id}.csv",
                    )
                    _df.index = np.arange(1, len(_df) + 1)
                    _df.to_csv(_params_fp, index_label="draw")

                # Track cumulative capex (components 1+2) across years for maintenance calc
                cumulative_capex = np.zeros(nsims)

                # Accumulate raw LM capex/opex per year for inventory model (applied after loop)
                lm_raw_capex = np.zeros((len(iv_years), nsims))
                lm_raw_opex = np.zeros((len(iv_years), nsims))

                # Precompute per-reefset intervention years so CAPEX comparison
                # uses the previous year for the same reefset, not a global iv_yr - 1.
                reefset_years_map = {}
                for rs in ID_key.loc[rep_idx, "reefset"].unique():
                    rs_mask = rep_idx & (ID_key.reefset == rs)
                    reefset_years_map[rs] = sorted(
                        ID_key.loc[rs_mask, "intervention_years"].unique()
                    )

                for iv_yr in iv_years:
                    curr_selector = (ID_key.intervention_years == iv_yr) & rep_idx
                    iv_type = ID_key.loc[curr_selector.idxmax(), "type"]
                    yr_idx = iv_years.tolist().index(iv_yr)

                    # Reefsets active in this year — run the model once per reefset
                    # and accumulate costs so multi-region deployments are summed.
                    reefsets_this_yr = ID_key.loc[curr_selector, "reefset"].unique()

                    if iv_type == "outplant":
                        yr_capex = np.zeros(nsims)
                        yr_opex = np.zeros(nsims)

                        for rs in reefsets_this_yr:
                            rs_selector = curr_selector & (ID_key.reefset == rs)
                            rs_spec = ID_key.loc[
                                rs_selector,
                                [
                                    "number_of_1YO_corals",
                                    "distance_to_port_NM",
                                    "number_of_groups",
                                    "rep",
                                ],
                            ]
                            departure_port = ID_key.loc[rs_selector.idxmax(), "port_name"]

                            prod_factors, deploy_factors = update_factors(
                                prod_factors, deploy_factors, rs_spec
                            )
                            deploy_wb, deploy_factors = collect_deployment_costs(
                                xlapp,
                                deploy_wb,
                                deploy_model_fp,
                                deploy_factors,
                                deploy_spec,
                            )
                            prod_wb, prod_factors = collect_production_costs(
                                xlapp, prod_wb, prod_model_fp, prod_factors, prod_spec
                            )

                            # CAPEX comparison against the previous year this reefset
                            # was active (not necessarily iv_yr - 1 globally).
                            rs_years = reefset_years_map[rs]
                            rs_yr_idx = rs_years.index(iv_yr)
                            if rs_yr_idx > 0:
                                prev_rs_yr = rs_years[rs_yr_idx - 1]
                                prev_selector = (
                                    (ID_key.intervention_years == prev_rs_yr)
                                    & rep_idx
                                    & (ID_key.reefset == rs)
                                )

                                curr_devices = (
                                    deploy_factors["num_1yoec"].values[0:nsims].copy()
                                )
                                prev_devices = calc_production_requirement(
                                    deploy_factors,
                                    ID_key.loc[
                                        prev_selector, ["number_of_1YO_corals", "rep"]
                                    ],
                                )

                                additional = np.maximum(curr_devices - prev_devices, 0)
                                no_additional = additional == 0
                                if no_additional.any():
                                    prod_factors.loc[no_additional, "capex"] = 0.0
                                    deploy_factors.loc[no_additional, "capex"] = 0.0

                                with_additional = ~no_additional
                                if with_additional.any():
                                    deploy_wb = reset_workbook(
                                        xlapp, deploy_wb, deploy_model_fp
                                    )
                                    prod_wb = reset_workbook(
                                        xlapp, prod_wb, prod_model_fp
                                    )

                                    deploy_factors.loc[with_additional, "num_1yoec"] = (
                                        additional[with_additional]
                                    )
                                    prod_factors.loc[with_additional, "num_1yoec"] = (
                                        additional[with_additional]
                                    )

                                    deploy_wb, updated_dep_cost = collect_deployment_costs(
                                        xlapp,
                                        deploy_wb,
                                        deploy_model_fp,
                                        deploy_factors.loc[with_additional, :],
                                        deploy_spec,
                                    )
                                    prod_wb, updated_prod_cost = collect_production_costs(
                                        xlapp,
                                        prod_wb,
                                        prod_model_fp,
                                        prod_factors.loc[with_additional, :],
                                        prod_spec,
                                    )

                                    prod_factors.loc[with_additional, "capex"] = (
                                        updated_prod_cost["capex"]
                                    )
                                    deploy_factors.loc[with_additional, "capex"] = (
                                        updated_dep_cost["capex"]
                                    )
                                    deploy_factors.loc[with_additional, "num_1yoec"] = (
                                        curr_devices[with_additional]
                                    )
                                    prod_factors.loc[with_additional, "num_1yoec"] = (
                                        curr_devices[with_additional]
                                    )

                            yr_capex += (
                                deploy_factors["capex"] + prod_factors["capex"]
                            ).values[0:nsims]
                            yr_opex += (
                                deploy_factors["opex"] + prod_factors["opex"]
                            ).values[0:nsims]

                            if rs_yr_idx > 0:
                                min_rs_yr = rs_years[0]
                                eia_template_prod = fill_EIA_info(
                                    prod_wb,
                                    "CA_P",
                                    rep,
                                    min_rs_yr,
                                    iv_yr,
                                    departure_port,
                                    eia_template_prod,
                                )
                                eia_template_deploy = fill_EIA_info(
                                    deploy_wb,
                                    "CA_D",
                                    rep,
                                    min_rs_yr,
                                    iv_yr,
                                    departure_port,
                                    eia_template_deploy,
                                )

                            deploy_wb = reset_workbook(xlapp, deploy_wb, deploy_model_fp)
                            prod_wb = reset_workbook(xlapp, prod_wb, prod_model_fp)

                        cost_sum = np.column_stack([yr_capex, yr_opex])

                        # Every 5th intervention year (relative to start), add 20% maintenance
                        # CAPEX on cumulative capex spent to date.
                        if yr_idx > 0 and yr_idx % 5 == 0:
                            maintenance = 0.20 * cumulative_capex
                            cost_sum[:, 0] = cost_sum[:, 0] + maintenance

                        component_costs = cost_types(cost_sum, cont_p, nsims)
                        cost_df.loc[cost_df.year == iv_yr, cost_df.columns[2:]] = (
                            component_costs
                        )
                        cumulative_capex = (
                            cumulative_capex + component_costs[0] + component_costs[1]
                        )

                    elif iv_type == "lm":
                        for rs in reefsets_this_yr:
                            rs_selector = curr_selector & (ID_key.reefset == rs)
                            departure_port = ID_key.loc[rs_selector.idxmax(), "port_name"]
                            rs_years = reefset_years_map[rs]
                            rs_yr_idx = rs_years.index(iv_yr)

                            lm_factors = update_lm_factors(
                                lm_factors,
                                ID_key.loc[
                                    rs_selector, ["number_of_1YO_corals", "rep"]
                                ],
                                lm_pool_min,
                                lm_pool_max,
                            )
                            lm_wb, lm_factors = collect_lm_costs(
                                xlapp, lm_wb, lm_model_fp, lm_factors, lm_spec
                            )
                            rs_distance = ID_key.loc[
                                rs_selector, "distance_to_port_NM"
                            ].iloc[0]
                            opex_mult = lm_opex_distance_multiplier(rs_distance)
                            lm_raw_capex[yr_idx] += lm_factors["capex"].values[0:nsims]
                            lm_raw_opex[yr_idx] += (
                                lm_factors["opex"].values[0:nsims] * opex_mult
                            )

                            if rs_yr_idx > 0:
                                eia_template_lm = fill_lm_EIA_info(
                                    lm_wb,
                                    "LM",
                                    rep,
                                    rs_years[0],
                                    iv_yr,
                                    departure_port,
                                    eia_template_lm,
                                )

                            lm_wb = reset_workbook(xlapp, lm_wb, lm_model_fp)

                # Apply inventory model per draw across the full year series,
                # then fold the resulting per-year total_capex and opex into cost_df.
                for draw_i in range(nsims):
                    draw_df = pd.DataFrame(
                        {
                            "capex": lm_raw_capex[:, draw_i],
                            "opex": lm_raw_opex[:, draw_i],
                            "corals": np.ones(
                                len(iv_years)
                            ),  # placeholder; ratio/average unused here
                        }
                    )
                    inv = _apply_lm_inventory_model(draw_df)
                    for yr_idx, iv_yr in enumerate(iv_years):
                        lm_cost_sum = np.array(
                            [
                                [
                                    inv["total_capex"].iloc[yr_idx],
                                    inv["opex"].iloc[yr_idx],
                                ]
                            ]
                        )
                        lm_components = cost_types(lm_cost_sum, cont_p, 1)
                        draw_col = f"draw{draw_i + 1}"
                        yr_mask = cost_df.year == iv_yr
                        cost_df.loc[yr_mask, draw_col] += lm_components[:, 0]

                rep_cost_dfs.append((rep, cost_df))

            # Merge per-rep cost dfs into one file; each rep's draws are renumbered
            # sequentially so rep columns never collide.
            draw_offset = 0
            combined = None
            for rep, cost_df in rep_cost_dfs:
                rep_draw_cols = [c for c in cost_df.columns if c.startswith("draw")]
                rename_map = {
                    c: f"draw{draw_offset + i + 1}" for i, c in enumerate(rep_draw_cols)
                }
                renamed = cost_df.rename(columns=rename_map)
                draw_offset += len(rep_draw_cols)
                if combined is None:
                    combined = renamed
                else:
                    new_draw_cols = list(rename_map.values())
                    combined = combined.merge(
                        renamed[["year", "component"] + new_draw_cols],
                        on=["year", "component"],
                    )

            cost_filepath = path_join(
                cost_dir,
                f"ID{scen_id}_intervention_cost_data_iter_pid{p_iter_id}.csv",
            )
            combined.to_csv(cost_filepath, index=False)
            cost_filepaths.append(cost_filepath)

            eia_template_prod = _fill_eia_missing_years(eia_template_prod, all_sim_years)
            eia_template_deploy = _fill_eia_missing_years(eia_template_deploy, all_sim_years)
            eia_template_lm = _fill_eia_missing_years(eia_template_lm, all_sim_years)

            eia_outputs = [
                (eia_template_prod, "production"),
                (eia_template_deploy, "deployment"),
            ]
            eia_outputs.append((eia_template_lm, "lm"))

            for eia_template, label in eia_outputs:
                cost_cols = eia_template.columns[5:]
                row_totals = (
                    eia_template[cost_cols]
                    .apply(pd.to_numeric, errors="coerce")
                    .sum(axis=1)
                )
                capex_mask = eia_template["type"].str.lower() == "capex"
                capex_row_totals = row_totals.where(capex_mask, 0.0).astype(float)
                cumulative_capex_col = (
                    eia_template.assign(_row_total=capex_row_totals)
                    .sort_values("year")
                    .groupby(["iteration", "intervention", "location"])["_row_total"]
                    .cumsum()
                    .reindex(eia_template.index)
                )
                eia_template["running_capex_total"] = cumulative_capex_col.where(
                    capex_mask, 0.0
                )
                eia_template.sort_values(
                    ["iteration", "intervention", "location", "year", "type"],
                    inplace=True,
                )
                eia_template.to_csv(
                    path_join(cost_dir, f"EIA_{scen_id}_{label}.csv"), index=False
                )
    finally:
        close_excel(xlapp, deploy_wb, quit_app=False)
        close_excel(xlapp, prod_wb, quit_app=False)
        close_excel(xlapp, lm_wb, quit_app=True)

    return cost_filepaths
