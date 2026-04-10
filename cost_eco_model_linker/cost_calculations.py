import dataclasses
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


# ---------------------------------------------------------------------------
# Cost component helpers
# ---------------------------------------------------------------------------


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
        # Apply convert_factor_types so categorical (integer) parameters are
        # stored as ints rather than floats, matching the Sobol path.
        factors_df_prod = convert_factor_types(
            pd.DataFrame(
                [dict(zip(specs_prod.factor_names, specs_prod.best_point_value))]
            ),
            specs_prod.is_cat,
        )
        factors_df_dep = convert_factor_types(
            pd.DataFrame(
                [dict(zip(specs_dep.factor_names, specs_dep.best_point_value))]
            ),
            specs_dep.is_cat,
        )
        factors_df_lm = convert_factor_types(
            pd.DataFrame([dict(zip(specs_lm.factor_names, specs_lm.best_point_value))]),
            specs_lm.is_cat,
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
    # Sum coral count over reefsets for this rep and year.
    # Convert to device count — the spreadsheet expects devices at the num_1yoec cell.
    n_1yo_corals = iv_spec["number_of_1YO_corals"].sum()
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
    Calculate the number of devices required in the previous intervention year
    for a single ecological repeat. Used to determine whether additional
    production capacity is needed in the current year.

    Parameters
    ----------
    deploy_factors : dataframe
        Factors dataframe for the deployment cost model (used for yield values).
    prev_iv_spec : dataframe
        Intervention specification dataframe for the previous intervention year
        and rep, containing one row per reefset.

    Returns
    -------
    prev_devices : np.ndarray
        Number of devices required in the previous intervention year, per simulation.
    """
    n_1yo_corals = prev_iv_spec["number_of_1YO_corals"].sum()
    return np.ceil(n_1yo_corals / deploy_factors["coral_yield_1YOEC"])


# ---------------------------------------------------------------------------
# Overview accumulator
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _OverviewAccumulator:
    """Per-rep arrays that accumulate costs and metadata for the overview CSV."""

    n_years: int
    nsims: int

    def __post_init__(self):
        n, s = self.n_years, self.nsims
        self.prod_raw_capex = np.zeros((n, s))
        self.prod_opex = np.zeros((n, s))
        self.deploy_raw_capex = np.zeros((n, s))
        self.deploy_opex = np.zeros((n, s))
        self.outplant_total_capex = np.zeros((n, s))
        self.num_devices = np.zeros((n, s))
        self.num_1yoec = np.zeros(n)  # scalar per year (not per draw)
        self.lm_num_larval_pool = np.zeros((n, s))
        self.lm_yield_per_pool = np.zeros((n, s))
        self.lm_raw_capex = np.zeros((n, s))
        self.lm_raw_opex = np.zeros((n, s))


# ---------------------------------------------------------------------------
# Private helpers extracted from calculate_costs()
# ---------------------------------------------------------------------------


def _copy_workbooks(tmp_dir, deploy_filepath, prod_filepath, lm_filepath, iter_id):
    """Copy the three Excel workbooks to a temporary directory for an isolated run.

    Returns
    -------
    deploy_fp, prod_fp, lm_fp : str
        Paths to the copied workbooks.
    """
    deploy_fp = path_join(tmp_dir, f"{deploy_filepath}{iter_id}.xlsx")
    os.makedirs(os.path.dirname(deploy_fp), exist_ok=True)
    shutil.copy(deploy_filepath + ".xlsx", deploy_fp)

    prod_fp = path_join(tmp_dir, f"{prod_filepath}{iter_id}.xlsx")
    os.makedirs(os.path.dirname(prod_fp), exist_ok=True)
    shutil.copy(prod_filepath + ".xlsx", prod_fp)

    lm_fp = path_join(tmp_dir, f"{lm_filepath}{iter_id}.xlsx")
    os.makedirs(os.path.dirname(lm_fp), exist_ok=True)
    shutil.copy(lm_filepath + ".xlsx", lm_fp)

    return deploy_fp, prod_fp, lm_fp


def _save_cost_params(
    cost_dir, scen_id, rep, p_iter_id, prod_factors, deploy_factors, lm_factors
):
    """Save sampled cost parameters to CSV for manual cross-checking.

    For production and deployment, a ``num_devices`` column derived from
    ``num_1yoec / coral_yield_1YOEC`` is inserted alongside ``num_1yoec``.
    """
    for _label, _df in [
        ("production", prod_factors),
        ("deployment", deploy_factors),
        ("lm", lm_factors),
    ]:
        _params_fp = path_join(
            cost_dir,
            f"ID{scen_id}_rep{rep}_cost_params_{_label}_pid{p_iter_id}.csv",
        )
        _save_df = _df.copy()
        if "num_1yoec" in _save_df.columns and "coral_yield_1YOEC" in _save_df.columns:
            _save_df.insert(
                _save_df.columns.get_loc("num_1yoec") + 1,
                "num_devices",
                np.ceil(_save_df["num_1yoec"] / _save_df["coral_yield_1YOEC"]).astype(
                    int
                ),
            )
        _save_df.index = np.arange(1, len(_save_df) + 1)
        _save_df.to_csv(_params_fp, index_label="draw")


def _process_outplant_reefset(
    xlapp,
    deploy_wb,
    prod_wb,
    deploy_model_fp,
    prod_model_fp,
    deploy_factors,
    deploy_spec,
    prod_factors,
    prod_spec,
    rs_spec,
    rs_num_1yoec,
    departure_port,
    rs_years,
    iv_yr,
    rep,
    nsims,
    yr_capex,
    yr_opex,
    acc,
    yr_idx,
    eia_template_prod,
    eia_template_deploy,
):
    """Run spreadsheet models for one outplant reefset and accumulate results.

    ``yr_capex``, ``yr_opex``, and ``acc`` are updated in-place.

    Parameters
    ----------
    rs_spec : DataFrame
        Rows from ID_key for this reefset/year/rep (columns: number_of_1YO_corals,
        distance_to_port_NM, number_of_groups, rep).
    rs_num_1yoec : float
        Sum of number_of_1YO_corals for this reefset (pre-computed by caller).
    yr_capex, yr_opex : np.ndarray shape (nsims,)
        Running totals across reefsets; modified in-place.
    acc : _OverviewAccumulator
        Overview tracking arrays; modified in-place.

    Returns
    -------
    deploy_wb, prod_wb, deploy_factors, prod_factors, eia_template_prod, eia_template_deploy
    """
    prod_factors, deploy_factors = update_factors(prod_factors, deploy_factors, rs_spec)
    deploy_wb, deploy_factors = collect_deployment_costs(
        xlapp, deploy_wb, deploy_model_fp, deploy_factors, deploy_spec
    )
    prod_wb, prod_factors = collect_production_costs(
        xlapp, prod_wb, prod_model_fp, prod_factors, prod_spec
    )

    # Capture raw values before the CAPEX comparison block
    # may modify them (raw = full spreadsheet run for this year).
    raw_prod_capex = prod_factors["capex"].values[0:nsims].copy()
    raw_deploy_capex = deploy_factors["capex"].values[0:nsims].copy()

    # CAPEX comparison block — commented out, superseded by inventory model.
    # To restore: also pass ID_key, rep_idx, rs, reefset_years_map to this function.
    # rs_yr_idx = rs_years.index(iv_yr)
    # if rs_yr_idx > 0:
    #     prior_years = rs_years[:rs_yr_idx]
    #     curr_devices = (
    #         deploy_factors["num_1yoec"]
    #         .values[0:nsims]
    #         .copy()
    #     )
    #     max_prior_devices = np.zeros(nsims)
    #     for prior_yr in prior_years:
    #         prior_selector = (
    #             (ID_key.intervention_years == prior_yr)
    #             & rep_idx
    #             & (ID_key.reefset == rs)
    #         )
    #         prior_devices = calc_production_requirement(
    #             deploy_factors,
    #             ID_key.loc[
    #                 prior_selector,
    #                 ["number_of_1YO_corals", "rep"],
    #             ],
    #         )
    #         max_prior_devices = np.maximum(
    #             max_prior_devices, prior_devices
    #         )
    #
    #     additional = np.maximum(
    #         curr_devices - max_prior_devices, 0
    #     )
    #     no_additional = additional == 0
    #     prod_factors.loc[:, "capex"] = np.where(
    #         no_additional, 0.0, raw_prod_capex
    #     )
    #     deploy_factors.loc[:, "capex"] = np.where(
    #         no_additional, 0.0, raw_deploy_capex
    #     )

    yr_capex += (deploy_factors["capex"] + prod_factors["capex"]).values[0:nsims]
    yr_opex += (deploy_factors["opex"] + prod_factors["opex"]).values[0:nsims]

    acc.prod_raw_capex[yr_idx] += raw_prod_capex
    acc.prod_opex[yr_idx] += prod_factors["opex"].values[0:nsims]
    acc.deploy_raw_capex[yr_idx] += raw_deploy_capex
    acc.deploy_opex[yr_idx] += deploy_factors["opex"].values[0:nsims]
    acc.num_devices[yr_idx] += deploy_factors["num_1yoec"].values[0:nsims]
    acc.num_1yoec[yr_idx] += rs_num_1yoec

    min_rs_yr = rs_years[0]
    eia_template_prod = fill_EIA_info(
        prod_wb, "CA_P", rep, min_rs_yr, iv_yr, "Townsville", eia_template_prod
    )
    eia_template_deploy = fill_EIA_info(
        deploy_wb, "CA_D", rep, min_rs_yr, iv_yr, departure_port, eia_template_deploy
    )

    deploy_wb = reset_workbook(xlapp, deploy_wb, deploy_model_fp)
    prod_wb = reset_workbook(xlapp, prod_wb, prod_model_fp)

    return (
        deploy_wb,
        prod_wb,
        deploy_factors,
        prod_factors,
        eia_template_prod,
        eia_template_deploy,
    )


def _process_lm_reefset(
    xlapp,
    lm_wb,
    lm_model_fp,
    lm_factors,
    lm_spec,
    lm_pool_min,
    lm_pool_max,
    rs_spec_corals,
    rs_distance,
    departure_port,
    rs_years,
    iv_yr,
    rep,
    nsims,
    acc,
    yr_idx,
    eia_template_lm,
):
    """Run the LM spreadsheet model for one reefset and accumulate results.

    ``acc`` is updated in-place.

    Parameters
    ----------
    rs_spec_corals : DataFrame
        Rows from ID_key for this reefset/year/rep (columns: number_of_1YO_corals, rep).
    rs_distance : float
        Distance from port in nautical miles for this reefset.
    acc : _OverviewAccumulator
        Overview tracking arrays; modified in-place.

    Returns
    -------
    lm_wb, lm_factors, eia_template_lm
    """
    lm_factors = update_lm_factors(lm_factors, rs_spec_corals, lm_pool_min, lm_pool_max)
    lm_wb, lm_factors = collect_lm_costs(xlapp, lm_wb, lm_model_fp, lm_factors, lm_spec)

    opex_mult = lm_opex_distance_multiplier(rs_distance)
    acc.lm_raw_capex[yr_idx] += lm_factors["capex"].values[0:nsims]
    acc.lm_raw_opex[yr_idx] += lm_factors["opex"].values[0:nsims] * opex_mult
    acc.lm_num_larval_pool[yr_idx] += lm_factors["larval release pools"].values[0:nsims]
    acc.lm_yield_per_pool[yr_idx] += lm_factors["yield_per_pool"].values[0:nsims]

    eia_template_lm = fill_lm_EIA_info(
        lm_wb, "LM", rep, rs_years[0], iv_yr, departure_port, eia_template_lm
    )
    lm_wb = reset_workbook(xlapp, lm_wb, lm_model_fp)

    return lm_wb, lm_factors, eia_template_lm


def _apply_outplant_inventory(yr_capex, outplant_inventory):
    """Apply the inventory/replacement model for outplant CAPEX.

    maintenance = 0.2 × inventory
    retained    = inventory − maintenance  (= 0.8 × inventory)

    * **Sufficient** (yr_capex ≤ retained): capex = 0, inventory decays to retained.
    * **Scaling up** (yr_capex > retained):
        capex     = (yr_capex − inventory) + maintenance  =  yr_capex − retained
        inventory = yr_capex

    Parameters
    ----------
    yr_capex : np.ndarray shape (nsims,)
        Full CAPEX requirement for this year across all reefsets.
    outplant_inventory : np.ndarray shape (nsims,)
        Accumulated inventory from prior years.

    Returns
    -------
    total_yr_capex : np.ndarray shape (nsims,)
    new_inventory : np.ndarray shape (nsims,)
    """
    maintenance = 0.2 * outplant_inventory
    retained = outplant_inventory - maintenance  # 0.8 × inventory
    needs_additional = yr_capex > retained
    total_yr_capex = np.where(
        needs_additional,
        (yr_capex - outplant_inventory) + maintenance,  # = yr_capex - retained
        0.0,
    )
    new_inventory = np.where(needs_additional, yr_capex, retained)
    return total_yr_capex, new_inventory


def _build_overview_rows_and_update_costs(
    cost_df, iv_years, nsims, acc, cont_p, scen_id, rep
):
    """Single pass over draws: apply LM inventory model, update cost_df, build overview rows.

    Combining these into one loop avoids calling ``_apply_lm_inventory_model`` twice
    per rep (once to fold into cost_df and once for the overview CSV).

    Parameters
    ----------
    cost_df : DataFrame
        Per-year cost dataframe for this rep; CAPEX/OPEX draw columns are updated in-place.
    iv_years : array-like
        Ordered intervention years for this scenario.
    acc : _OverviewAccumulator
        Accumulated raw values from the year loop.

    Returns
    -------
    overview_rows : list[dict]
    """
    overview_rows = []

    for draw_i in range(nsims):
        lm_inv = _apply_lm_inventory_model(
            pd.DataFrame(
                {
                    "capex": acc.lm_raw_capex[:, draw_i],
                    "opex": acc.lm_raw_opex[:, draw_i],
                    "corals": np.ones(len(iv_years)),
                }
            )
        )

        for yr_idx, iv_yr in enumerate(iv_years):
            # Fold LM inventory-adjusted costs into cost_df
            lm_cost_sum = np.array(
                [
                    [
                        float(lm_inv["total_capex"].iloc[yr_idx]),
                        float(lm_inv["opex"].iloc[yr_idx]),
                    ]
                ]
            )
            lm_components = cost_types(lm_cost_sum, cont_p, 1)
            draw_col = f"draw{draw_i + 1}"
            cost_df.loc[cost_df.year == iv_yr, draw_col] += lm_components[:, 0]

            # Build overview row
            # Post-inventory outplant capex is split proportionally to raw prod/deploy values.
            raw_prod = acc.prod_raw_capex[yr_idx, draw_i]
            raw_deploy = acc.deploy_raw_capex[yr_idx, draw_i]
            raw_total = raw_prod + raw_deploy
            prod_share = raw_prod / raw_total if raw_total > 0 else 0.5
            deploy_share = 1.0 - prod_share

            total_outplant = acc.outplant_total_capex[yr_idx, draw_i]
            post_prod_capex = total_outplant * prod_share
            post_deploy_capex = total_outplant * deploy_share

            lm_capex = float(lm_inv["total_capex"].iloc[yr_idx])
            lm_opex = float(lm_inv["opex"].iloc[yr_idx])
            subtotal_capex = post_prod_capex + post_deploy_capex
            subtotal_opex = (
                acc.prod_opex[yr_idx, draw_i] + acc.deploy_opex[yr_idx, draw_i]
            )

            overview_rows.append(
                {
                    "intervention_id": scen_id,
                    "rep_id": rep,
                    "draw": draw_i + 1,
                    "year": int(iv_yr),
                    "num_devices": acc.num_devices[yr_idx, draw_i],
                    "num_1yoec": acc.num_1yoec[yr_idx],
                    "num_larval_pool": acc.lm_num_larval_pool[yr_idx, draw_i],
                    "yield_per_pool": acc.lm_yield_per_pool[yr_idx, draw_i],
                    "production_capex": post_prod_capex,
                    "production_opex": acc.prod_opex[yr_idx, draw_i],
                    "deployment_capex": post_deploy_capex,
                    "deployment_opex": acc.deploy_opex[yr_idx, draw_i],
                    "lm_capex": lm_capex,
                    "lm_opex": lm_opex,
                    "subtotal_capex_CA_P_D": subtotal_capex,
                    "total_capex_CA_P_D_LM": subtotal_capex + lm_capex,
                    "subtotal_opex_CA_P_D": subtotal_opex,
                    "total_opex_CA_P_D_LM": subtotal_opex + lm_opex,
                }
            )

    return overview_rows


def _write_eia_outputs(
    cost_dir,
    scen_id,
    eia_template_prod,
    eia_template_deploy,
    eia_template_lm,
    all_sim_years,
):
    """Fill missing years, compute running CAPEX totals, and write EIA CSVs."""
    eia_template_prod = _fill_eia_missing_years(eia_template_prod, all_sim_years)
    eia_template_deploy = _fill_eia_missing_years(eia_template_deploy, all_sim_years)
    eia_template_lm = _fill_eia_missing_years(eia_template_lm, all_sim_years)

    for eia_template, label in [
        (eia_template_prod, "production"),
        (eia_template_deploy, "deployment"),
        (eia_template_lm, "lm"),
    ]:
        cost_cols = eia_template.columns[5:]
        row_totals = (
            eia_template[cost_cols].apply(pd.to_numeric, errors="coerce").sum(axis=1)
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
            ["iteration", "year", "intervention", "location", "type"],
            inplace=True,
        )
        eia_template.to_csv(
            path_join(cost_dir, f"EIA_{scen_id}_{label}.csv"), index=False
        )


def _merge_rep_costs(rep_cost_dfs):
    """Merge per-rep cost dataframes, renumbering draws sequentially across reps.

    Parameters
    ----------
    rep_cost_dfs : list[(rep, cost_df, overview_rows)]

    Returns
    -------
    combined : DataFrame
    all_overview_rows : list[dict]
    """
    draw_offset = 0
    combined = None
    all_overview_rows = []

    for _, cost_df, overview_rows in rep_cost_dfs:
        all_overview_rows.extend(overview_rows)
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

    return combined, all_overview_rows


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


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
    deploy_model_fp, prod_model_fp, lm_model_fp = _copy_workbooks(
        tmp_dir, deploy_model_filepath, prod_model_filepath, lm_model_filepath, _iter_id
    )

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
            # Output EIA assessment for each intervention scenario
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

                # Apply the actual port distance to deploy_factors before saving so
                # the CSV reflects the value used in the simulation, not the config
                # best-point. Use the first reefset of the first intervention year as
                # representative (distance is fixed per reefset across years).
                _first_yr = iv_years[0]
                _first_rs = ID_key.loc[
                    (ID_key.intervention_years == _first_yr) & rep_idx, "reefset"
                ].iloc[0]
                _first_distance = ID_key.loc[
                    (ID_key.intervention_years == _first_yr)
                    & rep_idx
                    & (ID_key.reefset == _first_rs),
                    "distance_to_port_NM",
                ].iloc[0]
                deploy_factors.loc[:, "distance_from_port"] = _first_distance

                _save_cost_params(
                    cost_dir,
                    scen_id,
                    rep,
                    p_iter_id,
                    prod_factors,
                    deploy_factors,
                    lm_factors,
                )

                # Track outplant CAPEX inventory across years for the inventory/replacement model
                outplant_inventory = np.zeros(nsims)

                # Accumulate costs and metadata across years for the overview CSV
                acc = _OverviewAccumulator(n_years=len(iv_years), nsims=nsims)

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
                    yr_idx = iv_years.tolist().index(iv_yr)

                    iv_types_this_yr = (
                        ID_key.loc[curr_selector, "type"].str.lower().unique()
                    )

                    for iv_type in iv_types_this_yr:
                        # Reefsets active in this year for this type — run the model once
                        # per reefset and accumulate costs so multi-region deployments are summed.
                        reefsets_this_yr = ID_key.loc[
                            curr_selector & (ID_key["type"].str.lower() == iv_type),
                            "reefset",
                        ].unique()

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
                                departure_port = ID_key.loc[
                                    rs_selector.idxmax(), "port_name"
                                ]
                                rs_num_1yoec = ID_key.loc[
                                    rs_selector, "number_of_1YO_corals"
                                ].sum()

                                (
                                    deploy_wb,
                                    prod_wb,
                                    deploy_factors,
                                    prod_factors,
                                    eia_template_prod,
                                    eia_template_deploy,
                                ) = _process_outplant_reefset(
                                    xlapp,
                                    deploy_wb,
                                    prod_wb,
                                    deploy_model_fp,
                                    prod_model_fp,
                                    deploy_factors,
                                    deploy_spec,
                                    prod_factors,
                                    prod_spec,
                                    rs_spec,
                                    rs_num_1yoec,
                                    departure_port,
                                    reefset_years_map[rs],
                                    iv_yr,
                                    rep,
                                    nsims,
                                    yr_capex,
                                    yr_opex,
                                    acc,
                                    yr_idx,
                                    eia_template_prod,
                                    eia_template_deploy,
                                )

                            # Inventory/replacement model applied across all reefsets for this year
                            total_yr_capex, outplant_inventory = (
                                _apply_outplant_inventory(yr_capex, outplant_inventory)
                            )
                            acc.outplant_total_capex[yr_idx] = total_yr_capex

                            cost_sum = np.column_stack([total_yr_capex, yr_opex])
                            component_costs = cost_types(cost_sum, cont_p, nsims)
                            cost_df.loc[cost_df.year == iv_yr, cost_df.columns[2:]] = (
                                component_costs
                            )

                        elif iv_type == "lm":
                            for rs in reefsets_this_yr:
                                rs_selector = curr_selector & (ID_key.reefset == rs)
                                departure_port = ID_key.loc[
                                    rs_selector.idxmax(), "port_name"
                                ]
                                rs_distance = ID_key.loc[
                                    rs_selector, "distance_to_port_NM"
                                ].iloc[0]

                                lm_wb, lm_factors, eia_template_lm = (
                                    _process_lm_reefset(
                                        xlapp,
                                        lm_wb,
                                        lm_model_fp,
                                        lm_factors,
                                        lm_spec,
                                        lm_pool_min,
                                        lm_pool_max,
                                        ID_key.loc[
                                            rs_selector, ["number_of_1YO_corals", "rep"]
                                        ],
                                        rs_distance,
                                        departure_port,
                                        reefset_years_map[rs],
                                        iv_yr,
                                        rep,
                                        nsims,
                                        acc,
                                        yr_idx,
                                        eia_template_lm,
                                    )
                                )

                        else:
                            raise ValueError(
                                "Unknown intervention type encountered. Must be one of 'outplant' or 'lm'."
                            )

                # Single pass over draws: fold LM inventory costs into cost_df and build overview rows
                overview_rows = _build_overview_rows_and_update_costs(
                    cost_df, iv_years, nsims, acc, cont_p, scen_id, rep
                )

                rep_cost_dfs.append((rep, cost_df, overview_rows))

            combined, all_overview_rows = _merge_rep_costs(rep_cost_dfs)

            combined["year"] = combined["year"].astype(int)
            combined["component"] = combined["component"].astype(int)

            cost_filepath = path_join(
                cost_dir,
                f"ID{scen_id}_intervention_cost_data_iter_pid{p_iter_id}.csv",
            )
            combined.to_csv(cost_filepath, index=False)
            cost_filepaths.append(cost_filepath)

            if all_overview_rows:
                overview_df = (
                    pd.DataFrame(all_overview_rows)
                    .sort_values(["intervention_id", "rep_id", "year"])
                    .reset_index(drop=True)
                )
                overview_df.to_csv(
                    path_join(
                        cost_dir,
                        f"ID{scen_id}_cost_overview_iter_pid{p_iter_id}.csv",
                    ),
                    index=False,
                )

            _write_eia_outputs(
                cost_dir,
                scen_id,
                eia_template_prod,
                eia_template_deploy,
                eia_template_lm,
                all_sim_years,
            )

    finally:
        close_excel(xlapp, deploy_wb, quit_app=False)
        close_excel(xlapp, prod_wb, quit_app=False)
        close_excel(xlapp, lm_wb, quit_app=True)

    return cost_filepaths
