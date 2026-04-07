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

    region = initial_header.CurrentRegion

    # Explicitly define the range from the header row to the bottom of the region
    start_cell = ws.Cells(initial_header.Row, region.Column)
    end_cell = ws.Cells(
        region.Row + region.Rows.Count - 1, region.Column + region.Columns.Count - 1
    )
    table_range = ws.Range(start_cell, end_cell)

    data = table_range.Value
    df = pd.DataFrame(data[1:], columns=data[0])
    # Drop columns that are entirely empty (e.g. "batch" in the production model)
    # before dropping rows with any NA, to avoid losing valid data rows.
    df = df.dropna(axis=1, how="all").dropna().reset_index(drop=True)
    # If duplicate column names exist (e.g. two "Cost" columns), keep the last occurrence
    return df.loc[:, ~df.columns.duplicated(keep="last")]


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

    type_header = ws.Cells.Find("Type")
    type_data = type_header.CurrentRegion.Value
    dt = (
        pd.DataFrame(type_data[1:], columns=type_data[0])["Type"]
        .dropna()
        .reset_index(drop=True)
    )

    cost_data = pd.DataFrame(data[1:], columns=data[0]).dropna().reset_index(drop=True)
    cost_data.loc[:, "Type"] = dt

    return cost_data


def create_eia_template(wb):
    # Setup EIA template
    eia_template = pd.DataFrame(
        columns=[
            "iteration",
            "year",
            "intervention",
            "location",
            "type",
        ]
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
        & (eia_template.distance == dest)
        & (eia_template.port == port)
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
    """Returns dict of common filter combinations.

    Filters based on entries in the `Type` column in CAPEX and OPEX spreadsheets
    of the cost models.
    """
    filters = {
        "passive": cost_type_df.Type.isin(["Facility", "Storage", "Technology"]),
        "passive_opex": cost_type_df.Type.isin(["Materials", "Facility"]),
        "labor": (cost_type_df.Type == "Active Labour")
        | (cost_type_df.Type == "Passive Labour"),
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
    """Single-pass update of industry costs in EIA template. Accumulates into existing values."""
    for code in unique_ind_codes:
        matches_code = ind_codes[df.index] == code

        if matches_code.sum() == 0:
            # Protect against no match
            continue

        if code not in eia_template.columns:
            eia_template[code] = 0.0

        existing = eia_template.loc[next_idx, code]
        existing = float(existing) if pd.notna(existing) else 0.0

        try:
            eia_template.loc[next_idx, code] = existing + float(
                df.loc[matches_code & cost_filter, "Cost"].sum()
            )
        except KeyError:
            eia_template.loc[next_idx, code] = existing + float(
                df.loc[matches_code & cost_filter, "Cost/all"].sum()
            )


def fill_opex(it, _, year, dest, port, eia_template, wb, attribution=None):
    """
    attribution : One of ["COLLECT", "RETURN", None], see `Attribution` column in Excel worksheets.
    """
    sheet_name = "Batch OPEX"
    cost_df, ind_codes, unique_ind_codes, next_idx = _setup_EIA_calculation(
        wb, sheet_name, eia_template, it, year, dest, port, "OPEX"
    )

    cost_type_df = find_table(wb.Sheets(sheet_name), "Amount")
    filters = create_cost_filters(cost_type_df, attribution)

    existing_labour = eia_template.loc[next_idx, "labour"]
    labor_costs = float(existing_labour) if pd.notna(existing_labour) else 0.0

    for code in unique_ind_codes:
        matches_code = ind_codes[cost_df.index] == code

        if code not in eia_template.columns:
            eia_template[code] = 0.0

        # Passive costs per industry (accumulate into existing)
        passive_sel = matches_code & filters["passive_opex"] & filters["attr"]
        existing = eia_template.loc[next_idx, code]
        existing = float(existing) if pd.notna(existing) else 0.0
        eia_template.loc[next_idx, code] = existing + float(cost_df.loc[passive_sel, "Cost"].sum())

        # Accumulate labor costs
        labor_sel = matches_code & filters["labor"] & filters["attr"]
        labor_costs += float(cost_df.loc[labor_sel, "Cost"].sum())

    eia_template.loc[next_idx, "labour"] = labor_costs
    eia_template.fillna(0.0, inplace=True)

    return eia_template


def fill_capex(it, _, year, dest, port, eia_template, wb, attribution=None):
    """
    attribution : One of ["COLLECT", "RETURN"], see `Attribution` column in Excel worksheets.
    """
    sheet_name = "Scale CAPEX"
    cost_df, ind_codes, unique_ind_codes, next_idx = _setup_EIA_calculation(
        wb, sheet_name, eia_template, it, year, dest, port, "CAPEX"
    )

    cost_type_df = find_table(wb.Sheets(sheet_name), "Resource")
    filters = create_cost_filters(cost_type_df, attribution)
    fill_industry_costs(
        eia_template,
        next_idx,
        cost_df,
        ind_codes,
        unique_ind_codes,
        filters["passive"] & filters["attr"],
    )

    # Accumulate labour costs (active + passive) across all industry codes, adding to existing
    existing_labour = eia_template.loc[next_idx, "labour"]
    labor_costs = float(existing_labour) if pd.notna(existing_labour) else 0.0
    for code in unique_ind_codes:
        matches_code = ind_codes[cost_df.index] == code
        labor_sel = matches_code & filters["labor"] & filters["attr"]
        try:
            labor_costs += float(cost_df.loc[labor_sel, "Cost"].sum())
        except KeyError:
            labor_costs += float(cost_df.loc[labor_sel, "Cost/all"].sum())

    eia_template.loc[next_idx, "labour"] = labor_costs
    eia_template.fillna(0.0, inplace=True)

    return eia_template


def _process_cost_section(
    eia_template,
    wb,
    shared_args,
    collect_return_flag=None,
):
    """Process a single cost section (Collection, Return, Production, or Deployment).

    Accumulates CAPEX and OPEX into the single 'Capex' and 'Opex' rows for the
    given (iteration, year, distance, port) combination.
    """
    eia_template = fill_capex(*shared_args, eia_template, wb, collect_return_flag)
    eia_template = fill_opex(*shared_args, eia_template, wb, collect_return_flag)

    return eia_template


def fill_EIA_info(
    prod_wb,
    deploy_wb,
    it: int,
    iv_start_year: int,
    year: int,
    dest: str,
    port: str,
    eia_template: pd.DataFrame,
):
    """
    Fill EIA template with cost data.

    Parameters
    ----------
    prod_wb :
        Production model
    deploy_wb :
        Deployment model
    it : int
        ReefMod Engine Iteration ID
    iv_start_year: int
        Year interventions begin
    year : int
        Simulation year
    dest : str
        Deployment destination
    port : str
        Port where deployments launched from
    eia_template : pd.DataFrame
        Template to fill
    """
    shared_args = (it, iv_start_year, year, dest, port)

    # Process production sections (Collection, Return, Production)
    for wb, flag in [
        (prod_wb, "COLLECT"),
        (prod_wb, "RETURN"),
        (prod_wb, None),
        (deploy_wb, None),
    ]:
        eia_template = _process_cost_section(eia_template, wb, shared_args, flag)

    # Adjust CAPEX costs relative to initial intervention year.
    # CAPEX is a one-time setup cost; in subsequent years only the *incremental*
    # increase matters (i.e. the cost of scaling up from the initial deployment).
    if year > iv_start_year:
        this_year = eia_template.year == year
        init_year = eia_template.year == iv_start_year
        capex_rows = eia_template.expense_name == "CAPEX"

        this_row = this_year & capex_rows
        init_row = init_year & capex_rows
        incremental = (
            eia_template.iloc[this_row, 5:].values
            - eia_template.iloc[init_row, 5:].values
        )
        eia_template.iloc[this_row, 5:] = incremental.clip(min=0)

    # Move labour column to last position
    eia_template["labour"] = eia_template.pop("labour")

    return eia_template
