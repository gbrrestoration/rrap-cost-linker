"""
Regression test: scaled EIA totals must match the cost overview for the same run.

For each model (production, deployment, LM) and expense type (Capex, Opex),
the ``total`` column in the scaled EIA file must equal the corresponding column
in the cost overview for every (year, draw) combination.

Run after executing example_simple_assessment.py:

    pytest tests/test_eia_consistency.py

To test against a different output directory:

    pytest tests/test_eia_consistency.py --cost-output-dir /path/to/outputs --scenario-id 2
"""

import pandas as pd
import pytest


def _eia_totals(eia_df, expense_type):
    """Return a Series indexed by (year, iteration) with the scaled EIA total.

    Sums across locations in case multiple reefsets contribute to one year.
    """
    rows = eia_df[eia_df["type"].str.lower() == expense_type.lower()]
    return rows.groupby(["year", "iteration"])["total"].sum()


@pytest.mark.parametrize(
    "eia_label, expense_type, overview_col",
    [
        ("production", "capex", "production_capex"),
        ("production", "opex", "production_opex"),
        ("deployment", "capex", "deployment_capex"),
        ("deployment", "opex", "deployment_opex"),
        ("lm", "capex", "lm_capex"),
        ("lm", "opex", "lm_opex"),
    ],
)
def test_scaled_eia_totals_match_overview(
    cost_output_dir, scenario_id, eia_label, expense_type, overview_col
):
    overview_path = cost_output_dir / f"ID{scenario_id}_cost_overview.csv"
    eia_path = cost_output_dir / f"EIA_cost_scaled_ID{scenario_id}_{eia_label}.csv"

    if not overview_path.exists():
        pytest.skip(f"Overview file not found: {overview_path}")
    if not eia_path.exists():
        pytest.skip(f"EIA scaled file not found: {eia_path}")

    # TODO: both reads could be moved to module-scoped fixtures to avoid reloading
    # the same files once per parametrised case.
    overview = pd.read_csv(overview_path)
    eia_df = pd.read_csv(eia_path)

    eia_totals = _eia_totals(eia_df, expense_type)

    mismatches = []
    for _, row in overview.iterrows():
        year, draw = int(row["year"]), int(row["draw"])
        expected = float(row[overview_col])
        actual = float(eia_totals.get((year, draw), 0.0))

        if abs(actual - expected) > 0.01:  # 1 cent tolerance for floating-point noise
            mismatches.append(
                f"  year={year} draw={draw}: EIA scaled={actual:.4f}, overview={expected:.4f}"
            )

    assert not mismatches, (
        f"{eia_label} {expense_type} mismatches ({len(mismatches)} rows):\n"
        + "\n".join(mismatches)
    )
