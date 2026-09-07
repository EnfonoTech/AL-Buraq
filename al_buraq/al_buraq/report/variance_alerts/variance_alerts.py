# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

"""
Variance Alerts — Cost Centres/Accounts where Actual to Date has already
exceeded the Accumulated Budget (the Monthly Distribution-weighted Budget
for every month up to and including As Of Date).

This is a deliberately tighter, earlier-warning check than comparing
Actual against the full-year Budget (that's what Available to Spend and
Budget Variance with Commitment already do) — a Cost Centre can be well
within its annual Budget and still be alerted here if it is spending
faster than its own Monthly Distribution says it should be, at this point
in the year.
"""

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate, nowdate

from al_buraq.al_buraq.report.rolling_forecast.rolling_forecast import _get_month_bounds
from al_buraq.utils.budget_common import get_actual_map, get_budget_map, get_dimension_config


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	columns = get_columns(filters)
	data = get_data(filters)
	message = get_message(filters)

	return columns, data, message


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))
	if not filters.get("fiscal_year"):
		frappe.throw(_("Fiscal Year is mandatory"))
	filters.setdefault("budget_against", "Cost Center")
	filters.setdefault("as_of_date", nowdate())
	get_dimension_config(filters.budget_against)


def get_columns(filters):
	dimension_label = filters.budget_against
	return [
		{
			"label": _(dimension_label),
			"fieldname": "dimension",
			"fieldtype": "Link",
			"options": dimension_label,
			"width": 160,
		},
		{"label": _("Account"), "fieldname": "account", "fieldtype": "Link", "options": "Account", "width": 160},
		{"label": _("Accumulated Budget"), "fieldname": "accumulated_budget", "fieldtype": "Currency", "width": 150},
		{"label": _("Actual to Date"), "fieldname": "actual_to_date", "fieldtype": "Currency", "width": 150},
		{"label": _("Variance"), "fieldname": "variance", "fieldtype": "Currency", "width": 130},
		{"label": _("Variance %"), "fieldname": "variance_percent", "fieldtype": "Percent", "width": 100},
		{"label": _("Alert Count"), "fieldname": "alert_count", "fieldtype": "Int", "hidden": 1, "width": 1},
	]


def get_data(filters):
	base_filters = frappe._dict(
		company=filters.company,
		budget_against=filters.budget_against,
		from_fiscal_year=filters.fiscal_year,
		to_fiscal_year=filters.fiscal_year,
		budget_against_filter=filters.get("budget_against_filter"),
		account=filters.get("account"),
	)
	budget_map = get_budget_map(base_filters)

	relevant_accounts = {k[1] for k in budget_map}
	if filters.get("account"):
		relevant_accounts |= set(filters.account)
	actual_map = get_actual_map(base_filters, relevant_accounts)

	row_keys = set(budget_map)
	if filters.get("budget_against_filter"):
		row_keys = {k for k in row_keys if k[0] in filters.budget_against_filter}
	if filters.get("account"):
		row_keys = {k for k in row_keys if k[1] in set(filters.account)}

	as_of = getdate(filters.as_of_date)
	month_bounds = _get_month_bounds(filters.fiscal_year)
	elapsed_months = [month for month, (start, _end) in month_bounds.items() if start <= as_of]

	data = []
	for dimension, account in sorted(row_keys):
		budget_months = budget_map.get((dimension, account), {}).get(filters.fiscal_year, {})
		actual_months = actual_map.get((dimension, account), {}).get(filters.fiscal_year, {})

		accumulated_budget = sum(flt(budget_months.get(month, 0)) for month in elapsed_months)
		actual_to_date = sum(flt(actual_months.get(month, 0)) for month in elapsed_months)
		variance = actual_to_date - accumulated_budget

		if variance <= 0:
			continue

		data.append(
			{
				"dimension": dimension,
				"account": account,
				"accumulated_budget": accumulated_budget,
				"actual_to_date": actual_to_date,
				"variance": variance,
				"variance_percent": (variance / accumulated_budget * 100) if accumulated_budget else 0,
				"alert_count": 1,
			}
		)

	data.sort(key=lambda row: row["variance"], reverse=True)
	return data


def get_message(filters):
	return "<br>".join(
		[
			_("Accumulated Budget = Monthly Distribution-weighted Budget for every month up to and including {0}.").format(
				formatdate(filters.as_of_date)
			),
			_("Only combinations where Actual to Date exceeds the Accumulated Budget are listed — a tighter, earlier check than comparing against the full-year Budget."),
			_("Calculation-only: this reads Budget and GL Entry and writes nothing back."),
		]
	)
