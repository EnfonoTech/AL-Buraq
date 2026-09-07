# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

"""
Budget Variance with Commitment.

This does NOT reimplement the native Budget Variance Report — it calls
erpnext's own report functions directly (same Budget/Actual/Variance
numbers, same period logic, same N+1-per-budget-row query pattern the
native report already has) and appends two columns on top: Committed and
Available = Budget - Actual - Committed, for the most recent fiscal year
in the selected range. The native Budget Variance Report is untouched.

For a higher-performance alternative that recomputes Budget/Actual/
Committed/Available itself (fixed query count, no per-row GL query),
see the "Available to Spend" report.
"""

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.report.budget_variance_report.budget_variance_report import (
	get_chart_data,
	get_columns,
	get_cost_centers,
	get_dimension_account_month_map,
	get_final_data,
	get_fiscal_years,
)
from erpnext.controllers.trends import get_period_month_ranges

from al_buraq.utils.budget_common import MONTHS, get_committed_map, get_dimension_config

COMMITMENT_BASIS = "Expected Date"  # fixed default — see report message for why


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	# --- native report, unmodified ---
	columns = get_columns(filters)
	dimensions = filters.get("budget_against_filter") or get_cost_centers(filters)
	period_month_ranges = get_period_month_ranges(filters["period"], filters["from_fiscal_year"])
	cam_map = get_dimension_account_month_map(filters)

	data = []
	for dimension in dimensions:
		dimension_items = cam_map.get(dimension)
		if dimension_items:
			data = get_final_data(dimension, dimension_items, filters, period_month_ranges, data, 0)

	chart = get_chart_data(filters, columns, data)

	# --- appended: Committed + Available, for the latest selected fiscal year ---
	fiscal_years = get_fiscal_years(filters)
	latest_fiscal_year = fiscal_years[-1][0] if fiscal_years else filters.to_fiscal_year
	_append_commitment_columns(columns)
	_append_commitment_values(filters, data, cam_map, latest_fiscal_year)

	message = get_message(filters, latest_fiscal_year)

	return columns, data, message, chart


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))
	if not filters.get("from_fiscal_year") or not filters.get("to_fiscal_year"):
		frappe.throw(_("From Fiscal Year and To Fiscal Year are mandatory"))
	filters.setdefault("budget_against", "Cost Center")
	filters.setdefault("period", "Yearly")
	get_dimension_config(filters.budget_against)


def _append_commitment_columns(columns):
	columns.append({"label": _("Committed"), "fieldtype": "Currency", "fieldname": "committed", "width": 130})
	columns.append({"label": _("Available"), "fieldtype": "Currency", "fieldname": "available", "width": 130})


def _append_commitment_values(filters, data, cam_map, latest_fiscal_year):
	committed_filters = frappe._dict(
		company=filters.company,
		budget_against=filters.budget_against,
		fiscal_year=latest_fiscal_year,
		commitment_basis=COMMITMENT_BASIS,
		budget_against_filter=filters.get("budget_against_filter"),
	)
	committed_map = get_committed_map(committed_filters)

	for row in data:
		dimension, account = row[0], row[1]

		committed = sum(
			flt(bucket.get("po", 0)) + flt(bucket.get("mr", 0))
			for bucket in committed_map.get((dimension, account), {}).values()
		)

		year_data = cam_map.get(dimension, {}).get(account, {}).get(latest_fiscal_year, {})
		latest_budget = sum(flt(year_data.get(m, {}).get("target", 0)) for m in MONTHS)
		latest_actual = sum(flt(year_data.get(m, {}).get("actual", 0)) for m in MONTHS)
		available = latest_budget - latest_actual - committed

		row.append(committed)
		row.append(available)


def get_message(filters, latest_fiscal_year):
	return "<br>".join(
		[
			_("Committed and Available reflect the {0} fiscal year as of now (point-in-time), using open Purchase Orders + pending Material Requests, Expected Date basis, Expense accounts only.").format(
				latest_fiscal_year
			),
			_("Available = Budget − Actual − Committed, for {0} only, even when multiple fiscal years are shown.").format(latest_fiscal_year),
		]
	)
