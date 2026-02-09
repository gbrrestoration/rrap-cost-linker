import win32com.client as w32client

import pandas as pd


def get_industry_codes(ws: w32client.CDispatch):
    """
    Retrieve industry classification codes found in the given worksheet.

    Parameters
    ----------
    ws : win32com.client.CDispatch
        Excel WorkSheet object

    Returns
    -------
    List of industry classification codes
    """
    industry_code_header = ws.Cells.Find("Industry classification code")

    if industry_code_header:
        # Get start of data
        start_cell = ws.Cells(industry_code_header.Row + 1, industry_code_header.Column)

        # Select data region
        data_range = start_cell.CurrentRegion
        df = pd.DataFrame(data_range.Value[1:])
    else:
        raise ValueError("Could not find industry classification codes!")

    return df.iloc[:, 0].to_numpy()


def find_table(ws: w32client.CDispatch, first_header: str) -> pd.DataFrame:
    """
    Identifies and retrieves table in a given worksheet identified by its first header.
    Selects contiguous data regions.

    Note: Drops NA rows.

    Parameters
    ----------
    ws : w32client.CDispatch
        Excel worksheet

    first_header: str
        Header of first column
    """
    initial_header = ws.Cells.Find(first_header)
    if not initial_header:
        raise ValueError(f"Header {first_header} not found in given worksheet!")

    table_range = initial_header.CurrentRegion
    data = table_range.Value

    return pd.DataFrame(data[1:], columns=data[0]).dropna()


def find_cost_table(ws: w32client.CDispatch) -> pd.DataFrame:
    """
    Identifies and retrieves cost table based on initial header "Amount".
    Selects contiguous data regions.

    Note: Drops NA rows.

    Parameters
    ----------
    ws : w32client.CDispatch
        Excel worksheet
    """
    initial_header = ws.Cells.Find("Amount")
    if initial_header:
        second_header = ws.Cells.FindNext(initial_header)

        # Check that it is not the same
        if second_header.Address != initial_header.Address:
            target_header = second_header
        else:
            target_header = initial_header

    else:
        raise ValueError("Appropriate table could not be found!")

    table_range = target_header.CurrentRegion
    data = table_range.Value

    return pd.DataFrame(data[1:], columns=data[0]).dropna()


def create_eia_template(wb):
    # Setup EIA template
    eia_template = pd.DataFrame(
        columns=["iteration", "year", "Destination.reef", "Location", "expense_name"]
    )

    ws = wb.Sheets("Scale CAPEX")

    # Get industry codes
    ind_codes = get_industry_codes(ws)
    unique_ind_codes = pd.unique(ind_codes)

    # Fill industry codes for CAPEX
    ind_codes = get_industry_codes(ws)
    for code in unique_ind_codes:
        eia_template[code] = None

    # Fill industry codes for OPEX
    ws = wb.Sheets("Batch OPEX")
    ind_codes = get_industry_codes(ws)
    unique_ind_codes = pd.unique(ind_codes)
    for code in unique_ind_codes:
        eia_template[code] = None

    eia_template["labour"] = None

    return eia_template


def find_or_fill_row(eia_template, it, year, dest, port, expense):
    """
    Attempts to identify the matching row. If none found, adds a new row.
    Returns the row ID (of the existing row, or the new row).
    """
    if eia_template.empty:
        eia_template.loc[0] = [None] * len(eia_template.columns)
        return 0

    sel = (
        (eia_template.iteration == it)
        & (eia_template.year == year)
        & (eia_template.loc[:, "Destination.reef"] == dest)
        & (eia_template.Location == port)
        & (eia_template.expense_name == expense)
    )
    if sel.any():
        next_idx = sel.idxmax()
    else:
        next_idx = len(eia_template.index)
        eia_template.loc[next_idx] = [None] * len(eia_template.columns)

    return next_idx


def _setup_EIA_calculation(
    wb, sheet_name, eia_template, it, year, dest, port, expense_name
):
    """Common setup for deployment cost calculations"""
    ws = wb.Sheets(sheet_name)

    if sheet_name.lower() == "batch opex":
        cost_df = find_cost_table(ws)
    else:
        cost_df = find_table(ws, "Resource")

    ind_codes = get_industry_codes(ws)
    unique_ind_codes = pd.unique(ind_codes)

    next_idx = find_or_fill_row(eia_template, it, year, dest, port, expense_name)
    eia_template.iloc[next_idx, [0, 1, 2, 3, 4]] = (
        it,
        year,
        dest,
        port,
        expense_name,
    )

    return cost_df, ind_codes, unique_ind_codes, next_idx


def create_cost_filters(cost_type_df, attribution=None):
    """Returns dict of common filter combinations"""
    filters = {
        "passive": cost_type_df.Type.isin(["Facility", "Storage", "Technology"]),
        "passive_opex": cost_type_df.Type.isin(
            ["Materials", "Facility", "Passive Labour"]
        ),
        "active": cost_type_df.Type == "Active Labour",
    }

    if attribution:
        filters["attr"] = cost_type_df.Attribution == attribution
    else:
        filters["attr"] = (cost_type_df.Attribution != "COLLECT") & (
            cost_type_df.Attribution != "RETURN"
        )

    return filters


def fill_industry_costs(
    eia_template, next_idx, df, ind_codes, unique_ind_codes, cost_filter
):
    """Single-pass update of industry costs in EIA template"""
    for code in unique_ind_codes:
        matches_code = ind_codes[df.index] == code
        eia_template.loc[next_idx, code] = float(
            df.loc[matches_code & cost_filter, "Cost"].sum()
        )


def fill_opex(it, year, dest, port, eia_template, wb, expense, attribution=None):
    """
    attribution : One of ["COLLECT", "RETURN", None], see `Attribution` column in Excel worksheets.
    """
    sheet_name = "Batch OPEX"
    cost_df, ind_codes, unique_ind_codes, next_idx = _setup_EIA_calculation(
        wb, sheet_name, eia_template, it, year, dest, port, expense
    )

    cost_type_df = find_table(wb.Sheets(sheet_name), "Amount")
    filters = create_cost_filters(cost_type_df, attribution)

    active_costs = 0.0
    for code in unique_ind_codes:
        matches_code = ind_codes[cost_df.index] == code

        # Passive costs per industry
        passive_sel = matches_code & filters["passive_opex"] & filters["attr"]
        eia_template.loc[next_idx, code] = float(cost_df.loc[passive_sel, "Cost"].sum())

        # Accumulate active labor
        active_sel = matches_code & filters["active"] & filters["attr"]
        active_costs += float(cost_df.loc[active_sel, "Cost"].sum())

    eia_template.loc[next_idx, "labour"] = active_costs
    eia_template.fillna(0.0, inplace=True)
    return eia_template


def fill_capex(it, year, dest, port, eia_template, wb, expense, attribution=None):
    """
    attribution : One of ["COLLECT", "RETURN"], see `Attribution` column in Excel worksheets.
    """
    sheet_name = "Scale CAPEX"
    cost_df, ind_codes, unique_ind_codes, next_idx = _setup_EIA_calculation(
        wb, sheet_name, eia_template, it, year, dest, port, expense
    )

    cost_type_df = find_table(wb.Sheets(sheet_name), "Amount")

    filters = create_cost_filters(cost_type_df, attribution)
    fill_industry_costs(
        eia_template,
        next_idx,
        cost_df,
        ind_codes,
        unique_ind_codes,
        filters["passive"] & filters["attr"],
    )

    eia_template.fillna(0.0, inplace=True)

    return eia_template


def fill_total_costs(it, year, dest, port, eia_template, prefix):
    """
    Create total row by summing CAPEX and OPEX rows.

    Parameters
    ----------
    prefix : str
        Prefix for expense names (e.g., "3.0_Production" or "4.0_Deployment")
    """
    # Find existing CAPEX and OPEX rows
    capex_line = find_or_fill_row(eia_template, it, year, dest, port, f"{prefix}_Capex")
    opex_line = find_or_fill_row(eia_template, it, year, dest, port, f"{prefix}_Opex")

    # Create or find total row
    expense_name = f"{prefix}_Total_Capex_&_Opex"
    next_idx = find_or_fill_row(eia_template, it, year, dest, port, expense_name)

    # Fill metadata columns
    eia_template.iloc[next_idx, 0:5] = (it, year, dest, port, expense_name)

    # Sum cost columns
    eia_template.iloc[next_idx, 5:] = eia_template.iloc[capex_line, 5:].astype(
        float
    ) + eia_template.iloc[opex_line, 5:].astype(float)

    return eia_template


def fill_EIA_info(
    prod_wb,
    deploy_wb,
    it: int,
    year: int,
    dest: str,
    port: str,
    cost_adjustment_values,
    eia_template: pd.DataFrame,
):
    shared_args = (it, year, dest, port)

    # Collection
    eia_template = fill_capex(
        *shared_args, eia_template, prod_wb, "1.0_Coral_Collection_Capex", "COLLECT"
    )
    eia_template = fill_opex(
        *shared_args, eia_template, prod_wb, "1.0_Coral_Collection_Opex", "COLLECT"
    )
    eia_template = fill_total_costs(*shared_args, eia_template, "1.0_Coral_Collection")

    # Return
    eia_template = fill_capex(
        *shared_args, eia_template, prod_wb, "2.0_Coral_Return_Capex", "RETURN"
    )
    eia_template = fill_opex(
        *shared_args, eia_template, prod_wb, "2.0_Coral_Return_Opex", "RETURN"
    )
    eia_template = fill_total_costs(*shared_args, eia_template, "2.0_Coral_Return")

    # Production
    eia_template = fill_capex(
        *shared_args, eia_template, prod_wb, "3.0_Production_Capex"
    )
    eia_template = fill_opex(*shared_args, eia_template, prod_wb, "3.0_Production_Opex")
    eia_template = fill_total_costs(*shared_args, eia_template, "3.0_Production")

    eia_template = fill_capex(
        *shared_args, eia_template, prod_wb, "3.0_Production_Capex"
    )

    data_cols = slice(5, -1)
    if cost_adjustment_values[0, 0] == 0:
        # Set all production CAPEX rows to zero
        capex_rows = eia_template.expense_name.str.contains(
            "Collection_Capex|Return_Capex|Production_Capex"
        )
        eia_template.iloc[capex_rows, data_cols] = 0.0

    eia_template = fill_opex(*shared_args, eia_template, prod_wb, "3.0_Production_Opex")
    if cost_adjustment_values[0, 1] == 0:
        # Set all production OPEX rows to zero
        opex_rows = eia_template.expense_name.str.contains(
            "Collection_Opex|Return_Opex|Production_Opex"
        )
        eia_template.iloc[opex_rows, data_cols] = 0.0

    eia_template = fill_total_costs(*shared_args, eia_template, "3.0_Production")

    # Deployment
    eia_template = fill_capex(
        *shared_args, eia_template, deploy_wb, "4.0_Deployment_Capex"
    )

    if cost_adjustment_values[1, 0] == 0:
        # Set all deployment CAPEX rows to zero
        capex_rows = eia_template.expense_name.str.contains("Deployment_Capex")
        eia_template.iloc[capex_rows, data_cols] = 0.0

    eia_template = fill_opex(
        *shared_args, eia_template, deploy_wb, "4.0_Deployment_Opex"
    )

    if cost_adjustment_values[1, 1] == 0:
        # Set all deployment OPEX rows to zero
        opex_rows = eia_template.expense_name.str.contains("Deployment_Opex")
        eia_template.iloc[opex_rows, data_cols] = 0.0

    eia_template = fill_total_costs(*shared_args, eia_template, "4.0_Deployment")

    # Fill monitoring rows
    eia_template.loc[len(eia_template.index), :] = (
        *shared_args,
        "5.0_Monitor_Capex",
        *[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )

    eia_template.loc[len(eia_template.index), :] = (
        *shared_args,
        "5.0_Monitor_Opex",
        *[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )

    eia_template.loc[len(eia_template.index), :] = (
        *shared_args,
        "5.0_Monitor_Total_Capex_&_Opex",
        *[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )

    # Move Labour column to last position
    labour_col = eia_template.pop("labour")
    eia_template["labour"] = labour_col

    return eia_template
