# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate

from al_buraq.utils.budget_common import (
	get_actual_map,
	get_budget_map,
	get_committed_map,
	get_dimension_config,
	get_forecast_map,
	get_period_month_ranges_for,
	get_period_ranges,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	month_bounds = _get_month_bounds(filters.fiscal_year)
	columns = get_columns(filters)
	data = get_data(filters, month_bounds)
	message = get_message(filters)

	return columns, data, message


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))
	if not filters.get("fiscal_year"):
		frappe.throw(_("Fiscal Year is mandatory"))
	if not frappe.db.exists("Fiscal Year", filters.fiscal_year):
		frappe.throw(_("{0} is not a valid Fiscal Year").format(filters.fiscal_year))
	filters.setdefault("budget_against", "Cost Center")
	filters.setdefault("period", "Quarterly")
	filters.setdefault("actual_upto", frappe.utils.nowdate())
	filters.setdefault("current_period_basis", "Pro-rated Blend")
	filters.setdefault("show_budget", 1)
	filters.setdefault("commitment_basis", "Expected Date")
	get_dimension_config(filters.budget_against)


def _get_month_bounds(fiscal_year):
	months = get_period_month_ranges_for("Monthly", fiscal_year)
	date_ranges = get_period_ranges("Monthly", fiscal_year)
	return {group[0]: date_range for group, date_range in zip(months, date_ranges)}


def get_columns(filters):
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
	]

	for months, (from_date, to_date) in zip(
		get_period_month_ranges_for(filters.period, filters.fiscal_year), get_period_ranges(filters.period, filters.fiscal_year)
	):
		suffix = str(filters.fiscal_year) if filters.period == "Yearly" else formatdate(from_date, "MMM")

		if filters.show_budget:
			label = f"{_('Budget')} ({suffix})"
			columns.append({"label": label, "fieldname": frappe.scrub(label), "fieldtype": "Currency", "width": 120})

		if filters.get("show_actual_forecast_split"):
			for metric in (_("Actual"), _("Forecast")):
				label = f"{metric} ({suffix})"
				columns.append({"label": label, "fieldname": frappe.scrub(label), "fieldtype": "Currency", "width": 120})

		label = f"{_('Projected')} ({suffix})"
		columns.append({"label": label, "fieldname": frappe.scrub(label), "fieldtype": "Currency", "width": 120})

	columns += [
		{"label": _("Approved Budget"), "fieldname": "total_budget", "fieldtype": "Currency", "width": 130},
		{"label": _("Actual YTD"), "fieldname": "total_actual", "fieldtype": "Currency", "width": 130},
		{"label": _("Committed"), "fieldname": "total_committed", "fieldtype": "Currency", "width": 130},
		{"label": _("Total Forecast"), "fieldname": "total_forecast", "fieldtype": "Currency", "width": 130},
		{"label": _("Remaining Forecast"), "fieldname": "remaining_forecast", "fieldtype": "Currency", "width": 140},
		{"label": _("Latest Full-Year Forecast"), "fieldname": "total_projected", "fieldtype": "Currency", "width": 170},
		{"label": _("Forecast Variance"), "fieldname": "full_year_variance", "fieldtype": "Currency", "width": 140},
		{"label": _("Variance %"), "fieldname": "variance_percent", "fieldtype": "Percent", "width": 100},
		{"label": _("Forecast Source"), "fieldname": "forecast_source", "fieldtype": "Data", "width": 120},
	]

	if filters.get("compare_forecast_version"):
		columns += [
			{"label": _("Previous Forecast"), "fieldname": "previous_forecast", "fieldtype": "Currency", "width": 140},
			{"label": _("Change vs Previous Forecast"), "fieldname": "forecast_revision_amount", "fieldtype": "Currency", "width": 170},
		]

	return columns


def get_data(filters, month_bounds):
	base_filters = frappe._dict(
		company=filters.company,
		budget_against=filters.budget_against,
		fiscal_year=filters.fiscal_year,
		from_fiscal_year=filters.fiscal_year,
		to_fiscal_year=filters.fiscal_year,
		budget_against_filter=filters.get("budget_against_filter"),
		account=filters.get("account"),
		forecast_version=filters.get("forecast_version"),
	)

	budget_map = get_budget_map(base_filters)
	forecast_map = get_forecast_map(base_filters)

	previous_forecast_map = {}
	if filters.get("compare_forecast_version"):
		previous_forecast_map = get_forecast_map(frappe._dict(base_filters, forecast_version=filters.compare_forecast_version))

	relevant_accounts = {k[1] for k in budget_map} | {k[1] for k in forecast_map} | {k[1] for k in previous_forecast_map}
	if filters.get("account"):
		relevant_accounts |= set(filters.account)
	actual_map = get_actual_map(base_filters, relevant_accounts)

	committed_map = get_committed_map(
		frappe._dict(
			company=filters.company,
			budget_against=filters.budget_against,
			fiscal_year=filters.fiscal_year,
			commitment_basis=filters.commitment_basis,
			budget_against_filter=filters.get("budget_against_filter"),
			account=filters.get("account"),
		)
	)

	row_keys = set(budget_map) | set(forecast_map) | set(actual_map) | set(previous_forecast_map)
	if filters.get("budget_against_filter"):
		row_keys = {k for k in row_keys if k[0] in filters.budget_against_filter}
	if filters.get("account"):
		row_keys = {k for k in row_keys if k[1] in set(filters.account)}

	actual_upto = getdate(filters.actual_upto)

	data = []
	for dimension, account in sorted(row_keys):
		budget_months = budget_map.get((dimension, account), {}).get(filters.fiscal_year, {})
		actual_months = actual_map.get((dimension, account), {}).get(filters.fiscal_year, {})
		forecast_months = forecast_map.get((dimension, account), {})
		previous_forecast_months = previous_forecast_map.get((dimension, account), {})
		committed_months = committed_map.get((dimension, account), {})
		total_committed = sum(flt(b.get("po", 0)) + flt(b.get("mr", 0)) for b in committed_months.values())

		data.append(
			_build_row(
				filters,
				dimension,
				account,
				budget_months,
				actual_months,
				forecast_months,
				previous_forecast_months,
				total_committed,
				month_bounds,
				actual_upto,
			)
		)

	return data


def _projected_for_month(filters, month, budget_amount, actual_amount, forecast_amount, has_entered_forecast, bounds, actual_upto):
	from_date, to_date = bounds[month]

	if to_date <= actual_upto:
		return flt(actual_amount), "actual"

	forecast_or_fallback = flt(forecast_amount) if has_entered_forecast else flt(budget_amount)
	source = "entered" if has_entered_forecast else ("fallback" if budget_amount else "none")

	if from_date > actual_upto:
		return forecast_or_fallback, source

	# Straddling month: actual_upto falls inside [from_date, to_date]
	basis = filters.current_period_basis
	if basis == "Actual Only":
		return flt(actual_amount), "actual"
	if basis == "Forecast Only":
		return forecast_or_fallback, source

	days_in_month = (to_date - from_date).days + 1
	remaining_days = (to_date - actual_upto).days
	blended = flt(actual_amount) + forecast_or_fallback * remaining_days / days_in_month
	return blended, source


def _project_full_year(filters, budget_months, actual_months, forecast_months, month_bounds, actual_upto):
	"""Whole fiscal-year Projected total, independent of the report's
	period-grouping filter — used to score the comparison forecast version
	against the same actual_upto as the current one."""
	total = 0.0
	for month in month_bounds:
		budget_amount = flt(budget_months.get(month, 0))
		actual_amount = flt(actual_months.get(month, 0))
		has_entered = month in forecast_months
		forecast_amount = flt(forecast_months.get(month, 0))
		projected, _source = _projected_for_month(
			filters, month, budget_amount, actual_amount, forecast_amount, has_entered, month_bounds, actual_upto
		)
		total += projected
	return total


def _build_row(
	filters,
	dimension,
	account,
	budget_months,
	actual_months,
	forecast_months,
	previous_forecast_months,
	total_committed,
	month_bounds,
	actual_upto,
):
	row = {"dimension": dimension, "account": account}

	totals = {"budget": 0.0, "actual": 0.0, "forecast": 0.0, "projected": 0.0}
	sources_seen = set()

	for months, (from_date, to_date) in zip(
		get_period_month_ranges_for(filters.period, filters.fiscal_year), get_period_ranges(filters.period, filters.fiscal_year)
	):
		suffix = str(filters.fiscal_year) if filters.period == "Yearly" else formatdate(from_date, "MMM")
		period_budget = period_actual = period_forecast = period_projected = 0.0

		for month in months:
			budget_amount = flt(budget_months.get(month, 0))
			actual_amount = flt(actual_months.get(month, 0))
			has_entered = month in forecast_months
			forecast_amount = flt(forecast_months.get(month, 0))

			projected, source = _projected_for_month(
				filters, month, budget_amount, actual_amount, forecast_amount, has_entered, month_bounds, actual_upto
			)

			if month_bounds[month][1] > actual_upto:
				sources_seen.add(source)

			period_budget += budget_amount
			period_actual += actual_amount
			period_forecast += forecast_amount if has_entered else 0.0
			period_projected += projected

		if filters.show_budget:
			row[frappe.scrub(f"{_('Budget')} ({suffix})")] = period_budget
		if filters.get("show_actual_forecast_split"):
			row[frappe.scrub(f"{_('Actual')} ({suffix})")] = period_actual
			row[frappe.scrub(f"{_('Forecast')} ({suffix})")] = period_forecast
		row[frappe.scrub(f"{_('Projected')} ({suffix})")] = period_projected

		totals["budget"] += period_budget
		totals["actual"] += period_actual
		totals["forecast"] += period_forecast
		totals["projected"] += period_projected

	row["total_budget"] = totals["budget"]
	row["total_actual"] = totals["actual"]
	row["total_committed"] = total_committed
	row["total_forecast"] = totals["forecast"]
	row["remaining_forecast"] = totals["projected"] - totals["actual"]
	row["total_projected"] = totals["projected"]
	row["full_year_variance"] = totals["projected"] - totals["budget"]
	row["variance_percent"] = (row["full_year_variance"] / totals["budget"] * 100) if totals["budget"] else 0

	if filters.get("compare_forecast_version"):
		previous_total = _project_full_year(
			filters, budget_months, actual_months, previous_forecast_months, month_bounds, actual_upto
		)
		row["previous_forecast"] = previous_total
		row["forecast_revision_amount"] = totals["projected"] - previous_total

	if not sources_seen or sources_seen == {"actual"}:
		row["forecast_source"] = "-"
	elif sources_seen == {"entered"}:
		row["forecast_source"] = _("Entered")
	elif sources_seen == {"fallback"} or sources_seen == {"none"}:
		row["forecast_source"] = _("Budget Fallback")
	else:
		row["forecast_source"] = _("Mixed")

	return row


def get_message(filters):
	parts = [
		_("Latest Full-Year Forecast = Actual YTD (closed months as of {0}) + Remaining Forecast (Forecast Entry, or the distributed Budget where none was entered, for months still ahead).").format(
			formatdate(filters.actual_upto)
		),
		_("Forecast Variance = Latest Full-Year Forecast − Approved Budget: positive means the current forecast exceeds the approved Budget."),
		_("Committed is open Purchase Order/Material Request amount not yet billed, as of now (point-in-time, not spread across periods) — {0} basis.").format(filters.commitment_basis),
		_("Current-period basis: {0}.").format(filters.current_period_basis),
		_("Forecast Entry amounts are not rolled up through the Cost Center tree — a forecast only counts for the exact dimension it was entered against."),
	]
	if filters.get("compare_forecast_version"):
		parts.append(
			_("Previous Forecast re-scores Forecast Version '{0}' against the same Actual Upto date, so the two forecasts are compared on equal footing.").format(
				filters.compare_forecast_version
			)
		)
	return "<br>".join(parts)
