import frappe
from frappe import _
from frappe.utils import flt

from al_buraq.utils.budget_common import MONTHS, get_budget_map, get_dimension_config


@frappe.whitelist()
def get_budget_accounts(company, fiscal_year, budget_against, dimension):
    """
    Pre-fill Forecast Revision lines (one row per account per month, at
    the Budget's own monthly-distributed amount) from the native Budget for
    the given dimension/fiscal year. Used by the "Get Accounts from Budget"
    button — without it, entering a forecast by hand is hundreds of grid
    rows and the feature goes unused.
    """
    if not frappe.has_permission("Budget", "read"):
        frappe.throw(_("Not permitted to read Budget"), frappe.PermissionError)

    get_dimension_config(budget_against)  # raises for unsupported values
    filters = frappe._dict(
        company=company,
        budget_against=budget_against,
        from_fiscal_year=fiscal_year,
        to_fiscal_year=fiscal_year,
        budget_against_filter=[dimension],
    )
    budget_map = get_budget_map(filters)

    rows = []
    for (row_dimension, account), years in budget_map.items():
        if row_dimension != dimension:
            continue
        month_map = years.get(fiscal_year, {})
        for month in MONTHS:
            amount = flt(month_map.get(month))
            if amount:
                rows.append({"account": account, "month": month, "forecast_amount": amount})

    return rows
