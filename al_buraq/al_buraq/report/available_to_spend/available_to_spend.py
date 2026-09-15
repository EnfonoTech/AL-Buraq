# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, formatdate

from al_buraq.utils.budget_common import (
	get_actual_map,
	get_budget_map,
	get_committed_map_by_year,
	get_dimension_config,
	get_fiscal_years_between,
	get_period_month_ranges_for,
	get_period_ranges,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	fiscal_years = get_fiscal_years_between(filters.from_fiscal_year, filters.to_fiscal_year)
	columns = get_columns(filters, fiscal_years)
	data = get_data(filters, fiscal_years)
	chart = get_chart_data(filters, data)
	message = get_message(filters)

	return columns, data, message, chart


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))
	if not filters.get("from_fiscal_year") or not filters.get("to_fiscal_year"):
		frappe.throw(_("From Fiscal Year and To Fiscal Year are mandatory"))
	for fieldname in ("from_fiscal_year", "to_fiscal_year"):
		if not frappe.db.exists("Fiscal Year", filters.get(fieldname)):
			frappe.throw(_("{0} is not a valid Fiscal Year").format(filters.get(fieldname)))
	filters.setdefault("budget_against", "Cost Center")
	filters.setdefault("period", "Quarterly")
	filters.setdefault("commitment_basis", "Expected Date")
	get_dimension_config(filters.budget_against)


def get_columns(filters, fiscal_years):
	dimension_label = filters.budget_against

	columns = [
		{
			"label": _(dimension_label),
			"fieldname": "dimension",
			"fieldtype": "Link",
			"options": dimension_label,
			"width": 160,
		},
		{"label": _("Account"), "fieldname": "account", "fieldtype": "Link", "options": "Account", "width": 160},
		{"label": _("Budgeted"), "fieldname": "budgeted", "fieldtype": "Check", "width": 80},
	]

	for fiscal_year in fiscal_years:
		for from_date, to_date in get_period_ranges(filters.period, fiscal_year):
			if filters.period == "Yearly":
				suffix = str(fiscal_year)
			else:
				suffix = "(%s) %s" % (formatdate(from_date, "MMM"), fiscal_year)

			for metric in (_("Budget"), _("Actual"), _("Committed"), _("Available")):
				label = f"{metric} {suffix}"
				columns.append(
					{"label": label, "fieldname": frappe.scrub(label), "fieldtype": "Currency", "width": 130}
				)

	for label in (_("Total Budget"), _("Total Actual"), _("Total Committed"), _("Total Available")):
		columns.append(
			{"label": label, "fieldname": frappe.scrub(label), "fieldtype": "Currency", "width": 130}
		)
	columns.append(
		{"label": _("Utilisation %"), "fieldname": "utilisation_percent", "fieldtype": "Percent", "width": 100}
	)

	if filters.get("rollup_to_dimension"):
		columns = [c for c in columns if c["fieldname"] not in ("account", "budgeted")]
		columns.append({"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120})
		columns.append({"label": _("Count"), "fieldname": "count", "fieldtype": "Int", "hidden": 1, "width": 1})

	return columns


def get_data(filters, fiscal_years):
	budget_map = get_budget_map(
		frappe._dict(
			company=filters.company,
			budget_against=filters.budget_against,
			from_fiscal_year=filters.from_fiscal_year,
			to_fiscal_year=filters.to_fiscal_year,
			budget_against_filter=filters.get("budget_against_filter"),
			account=filters.get("account"),
		)
	)

	relevant_accounts = {key[1] for key in budget_map}
	if filters.get("account"):
		relevant_accounts |= set(filters.account)

	actual_map = get_actual_map(
		frappe._dict(
			company=filters.company,
			budget_against=filters.budget_against,
			from_fiscal_year=filters.from_fiscal_year,
			to_fiscal_year=filters.to_fiscal_year,
		),
		relevant_accounts,
	)

	committed_map = get_committed_map_by_year(
		frappe._dict(
			company=filters.company,
			budget_against=filters.budget_against,
			commitment_basis=filters.commitment_basis,
			budget_against_filter=filters.get("budget_against_filter"),
			account=filters.get("account"),
		),
		fiscal_years,
	)

	row_keys = set(budget_map) | set(actual_map) | set(committed_map)
	if filters.get("budget_against_filter"):
		row_keys = {k for k in row_keys if k[0] in filters.budget_against_filter}
	if filters.get("account"):
		row_keys = {k for k in row_keys if k[1] in set(filters.account)}

	data = []
	for dimension, account in sorted(row_keys):
		row = _build_row(
			filters, fiscal_years, dimension, account, budget_map, actual_map, committed_map
		)
		if filters.get("hide_zero_rows") and not row["_has_amount"]:
			continue
		del row["_has_amount"]
		data.append(row)

	if filters.get("rollup_to_dimension"):
		data = _rollup_to_dimension(data)
		for row in data:
			row["count"] = 1
		if filters.get("only_at_risk"):
			data = [r for r in data if r["status"] not in (_("OK"), _("No Budget"))]

	return data


# Utilisation thresholds match the report's own red/orange highlighting
# (see the .js formatter) so "Status" and the colour-coding always agree.
NEAR_LIMIT_THRESHOLD = 90
OVER_BUDGET_THRESHOLD = 100


def _rollup_to_dimension(rows):
	"""Collapse per-Account rows into one row per Cost Centre/Project —
	answers 'which dimensions are approaching or exceeding their available
	budget' without the reader having to sum accounts by hand."""
	skip_fields = {"dimension", "account", "budgeted", "utilisation_percent"}

	grouped = {}
	for row in rows:
		target = grouped.setdefault(row["dimension"], {"dimension": row["dimension"]})
		for fieldname, value in row.items():
			if fieldname in skip_fields:
				continue
			target[fieldname] = flt(target.get(fieldname, 0)) + flt(value)

	result = list(grouped.values())
	for row in result:
		total_budget = flt(row.get(frappe.scrub(_("Total Budget"))))
		total_actual = flt(row.get(frappe.scrub(_("Total Actual"))))
		total_committed = flt(row.get(frappe.scrub(_("Total Committed"))))
		spent = total_actual + total_committed

		row["utilisation_percent"] = (spent / total_budget * 100) if total_budget else 0
		row["status"] = _dimension_status(total_budget, spent, row["utilisation_percent"])

	return sorted(result, key=lambda r: r["utilisation_percent"], reverse=True)


def _dimension_status(total_budget, spent, utilisation_percent):
	if not total_budget:
		return _("Unbudgeted Spend") if spent else _("No Budget")
	if utilisation_percent >= OVER_BUDGET_THRESHOLD:
		return _("Over Budget")
	if utilisation_percent >= NEAR_LIMIT_THRESHOLD:
		return _("Near Limit")
	return _("OK")


def _build_row(filters, fiscal_years, dimension, account, budget_map, actual_map, committed_map):
	row = {
		"dimension": dimension,
		"account": account,
		"budgeted": 1 if (dimension, account) in budget_map else 0,
	}

	totals = {"budget": 0.0, "actual": 0.0, "committed": 0.0}
	has_amount = False
	carry_forward = 0.0

	for fiscal_year in fiscal_years:
		budget_year = budget_map.get((dimension, account), {}).get(fiscal_year, {})
		actual_year = actual_map.get((dimension, account), {}).get(fiscal_year, {})
		committed_year = committed_map.get((dimension, account), {}).get(fiscal_year, {})

		for months, (from_date, to_date) in zip(
			get_period_month_ranges_for(filters.period, fiscal_year), get_period_ranges(filters.period, fiscal_year)
		):
			period_budget = sum(flt(budget_year.get(m, 0)) for m in months)
			period_actual = sum(flt(actual_year.get(m, 0)) for m in months)
			period_committed = sum(
				flt(committed_year.get(m, {}).get("po", 0)) + flt(committed_year.get(m, {}).get("mr", 0))
				for m in months
			)

			if filters.get("show_cumulative"):
				period_budget += carry_forward

			period_available = period_budget - period_actual - period_committed

			if period_budget or period_actual or period_committed:
				has_amount = True

			if filters.period == "Yearly":
				suffix = str(fiscal_year)
			else:
				suffix = "(%s) %s" % (formatdate(from_date, "MMM"), fiscal_year)

			row[frappe.scrub(f"{_('Budget')} {suffix}")] = period_budget
			row[frappe.scrub(f"{_('Actual')} {suffix}")] = period_actual
			row[frappe.scrub(f"{_('Committed')} {suffix}")] = period_committed
			row[frappe.scrub(f"{_('Available')} {suffix}")] = period_available

			totals["budget"] += period_budget
			totals["actual"] += period_actual
			totals["committed"] += period_committed

			if filters.get("show_cumulative"):
				carry_forward = period_budget - period_actual - period_committed

	total_available = totals["budget"] - totals["actual"] - totals["committed"]
	row[frappe.scrub(_("Total Budget"))] = totals["budget"]
	row[frappe.scrub(_("Total Actual"))] = totals["actual"]
	row[frappe.scrub(_("Total Committed"))] = totals["committed"]
	row[frappe.scrub(_("Total Available"))] = total_available
	spent = totals["actual"] + totals["committed"]
	row["utilisation_percent"] = (spent / totals["budget"] * 100) if totals["budget"] else 0

	row["_has_amount"] = has_amount
	return row


def get_chart_data(filters, data):
	if not data:
		return None

	top_rows = sorted(data, key=lambda r: r.get("utilisation_percent", 0), reverse=True)[:10]
	if not top_rows or "utilisation_percent" not in top_rows[0]:
		return None

	return {
		"data": {
			"labels": [r["dimension"] for r in top_rows],
			"datasets": [{"name": _("Utilisation %"), "values": [r.get("utilisation_percent", 0) for r in top_rows]}],
		},
		"type": "bar",
	}


def get_message(filters):
	if filters.get("rollup_to_dimension"):
		parts = [
			_("One row per {0}, summed across every Account. Sorted by Utilisation % (highest first).").format(_(filters.budget_against)),
			_("Status: Over Budget (Utilisation ≥ {0}%), Near Limit (Utilisation ≥ {1}%), Unbudgeted Spend (spend/commitment with no Budget at all).").format(
				OVER_BUDGET_THRESHOLD, NEAR_LIMIT_THRESHOLD
			),
		]
	else:
		parts = [
			_("Available = Budget − Actual − Committed, per period."),
			_("Rows marked 'Budgeted' = 0 have spend/commitment but no native Budget entry — they would not appear on the native Budget Variance Report."),
			_("Committed excludes the already-billed portion of every Purchase Order/Material Request line (amount − billed_amt), so the same expenditure never counts as both Committed and Actual."),
			_("Click a Total Actual or Total Committed amount to drill into the GL Entries or the Committed Amount report behind it, for the same Cost Center/Project, Account and Fiscal Year range."),
		]
	if filters.get("show_cumulative"):
		parts.append(_("Cumulative: unspent budget from a period carries forward into the next period."))
	return "<br>".join(parts)
