# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate

from al_buraq.al_buraq.doctype.budget_scenario.budget_scenario import SPECIFICITY
from al_buraq.al_buraq.report.rolling_forecast.rolling_forecast import _get_month_bounds, _projected_for_month
from al_buraq.utils.budget_common import (
	MONTHS,
	get_actual_map,
	get_budget_map,
	get_dimension_config,
	get_forecast_map,
	get_period_month_ranges_for,
	get_period_ranges,
)

MAX_SCENARIOS = 3


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	scenarios = _get_scenarios(filters)
	if not scenarios:
		return [], [], _("No scenarios found for the given filters")

	base_on_values = {s.base_on for s in scenarios}
	baseline_source = scenarios[0].base_on
	warning = None
	if len(base_on_values) > 1:
		warning = _("Selected scenarios use different 'Base On' values — the Baseline column uses '{0}' (from {1}).").format(
			baseline_source, scenarios[0].name
		)

	columns = get_columns(filters, scenarios)
	data = get_data(filters, scenarios, baseline_source)
	message = get_message(filters, warning)

	return columns, data, message


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))
	if not filters.get("fiscal_year"):
		frappe.throw(_("Fiscal Year is mandatory"))
	if not filters.get("scenario"):
		frappe.throw(_("At least one Scenario is required"))
	if isinstance(filters.scenario, str):
		filters.scenario = [filters.scenario]
	if len(filters.scenario) > MAX_SCENARIOS:
		frappe.throw(_("Select at most {0} scenarios at a time").format(MAX_SCENARIOS))

	filters.setdefault("budget_against", "Cost Center")
	filters.setdefault("period", "Yearly")
	get_dimension_config(filters.budget_against)


def _get_scenarios(filters):
	rows = frappe.get_all(
		"Budget Scenario",
		filters={
			"name": ["in", filters.scenario],
			"company": filters.company,
			"fiscal_year": filters.fiscal_year,
			"budget_against": filters.budget_against,
		},
		fields=["name", "scenario_name", "base_on", "forecast_version"],
	)
	return rows


def _get_scenario_lines(scenario_names):
	if not scenario_names:
		return {}
	line = frappe.qb.DocType("Budget Scenario Line")
	rows = (
		frappe.qb.from_(line)
		.select(
			line.parent,
			line.apply_to,
			line.cost_center,
			line.project,
			line.account,
			line.adjustment_type,
			line.adjustment_value,
			line.period_scope,
			line.month,
		)
		.where(line.parent.isin(scenario_names))
		.run(as_dict=True)
	)
	lines_by_scenario = {}
	for row in rows:
		lines_by_scenario.setdefault(row.parent, []).append(row)
	return lines_by_scenario


def get_columns(filters, scenarios):
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
		suffix = "" if filters.period == "Yearly" else f" ({formatdate(from_date, 'MMM')})"

		columns.append(
			{"label": f"{_('Baseline')}{suffix}", "fieldname": frappe.scrub(f"baseline{suffix}"), "fieldtype": "Currency", "width": 130}
		)
		if filters.get("show_actual", 1):
			columns.append(
				{"label": f"{_('Actual YTD')}{suffix}", "fieldname": frappe.scrub(f"actual_ytd{suffix}"), "fieldtype": "Currency", "width": 130}
			)
		for scenario in scenarios:
			prefix = scenario.scenario_name
			columns += [
				{
					"label": f"{prefix} {_('Adjustment')}{suffix}",
					"fieldname": frappe.scrub(f"{prefix}_adjustment{suffix}"),
					"fieldtype": "Currency",
					"width": 130,
				},
				{
					"label": f"{prefix} {_('Budget')}{suffix}",
					"fieldname": frappe.scrub(f"{prefix}_budget{suffix}"),
					"fieldtype": "Currency",
					"width": 130,
				},
				{
					"label": f"{prefix} Δ%{suffix}",
					"fieldname": frappe.scrub(f"{prefix}_delta_percent{suffix}"),
					"fieldtype": "Percent",
					"width": 90,
				},
			]

	if filters.period != "Yearly":
		columns.append({"label": _("Baseline Total"), "fieldname": "baseline_total", "fieldtype": "Currency", "width": 130})
		for scenario in scenarios:
			columns.append(
				{
					"label": f"{scenario.scenario_name} {_('Total')}",
					"fieldname": frappe.scrub(f"{scenario.scenario_name}_total"),
					"fieldtype": "Currency",
					"width": 130,
				}
			)

	return columns


def get_data(filters, scenarios, baseline_source):
	base_filters = frappe._dict(
		company=filters.company,
		budget_against=filters.budget_against,
		fiscal_year=filters.fiscal_year,
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

	needs_forecast = baseline_source == "Rolling Forecast" or any(s.base_on == "Rolling Forecast" for s in scenarios)
	forecast_map = get_forecast_map(base_filters) if needs_forecast else {}

	lines_by_scenario = _get_scenario_lines([s.name for s in scenarios])
	month_bounds = _get_month_bounds(filters.fiscal_year)

	row_keys = set(budget_map) | set(actual_map) | set(forecast_map)
	if filters.get("budget_against_filter"):
		row_keys = {k for k in row_keys if k[0] in filters.budget_against_filter}
	if filters.get("account"):
		row_keys = {k for k in row_keys if k[1] in set(filters.account)}

	data = []
	for dimension, account in sorted(row_keys):
		row = _build_row(
			filters, dimension, account, scenarios, lines_by_scenario, baseline_source,
			budget_map, actual_map, forecast_map, month_bounds,
		)
		data.append(row)

	return data


def _monthly_baseline(base_on, dimension, account, fiscal_year, budget_map, actual_map, forecast_map, month_bounds):
	"""One month->amount map representing the baseline before any scenario adjustment."""
	if base_on == "Budget":
		return dict(budget_map.get((dimension, account), {}).get(fiscal_year, {}))

	if base_on == "Rolling Forecast":
		actual_upto = getdate()
		budget_months = budget_map.get((dimension, account), {}).get(fiscal_year, {})
		actual_months = actual_map.get((dimension, account), {}).get(fiscal_year, {})
		forecast_months = forecast_map.get((dimension, account), {})
		rf_filters = frappe._dict(current_period_basis="Pro-rated Blend")

		result = {}
		for month in MONTHS:
			budget_amount = flt(budget_months.get(month, 0))
			actual_amount = flt(actual_months.get(month, 0))
			has_entered = month in forecast_months
			forecast_amount = flt(forecast_months.get(month, 0))
			value, _source = _projected_for_month(
				rf_filters, month, budget_amount, actual_amount, forecast_amount, has_entered, month_bounds, actual_upto
			)
			result[month] = value
		return result

	# Actual (Annualised): no natural month bucketing, so the annualised
	# total is spread evenly across the 12 months for period grouping.
	actual_months = actual_map.get((dimension, account), {}).get(fiscal_year, {})
	actual_to_date = sum(flt(v) for v in actual_months.values())
	fy_start, fy_end = frappe.get_cached_value("Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"])
	today = getdate()
	days_elapsed = max(1, (min(today, fy_end) - fy_start).days + 1)
	days_in_year = (fy_end - fy_start).days + 1
	annualised = actual_to_date * days_in_year / days_elapsed
	return {month: annualised / 12 for month in MONTHS}


def _matching_lines(lines, budget_against, dimension, account):
	matches = []
	for line in lines:
		line_dimension = line.cost_center if budget_against == "Cost Center" else line.project
		if line.apply_to == "All":
			matches.append(line)
		elif line.apply_to == budget_against and line_dimension == dimension:
			matches.append(line)
		elif line.apply_to == f"{budget_against} + Account" and line_dimension == dimension and line.account == account:
			matches.append(line)
		elif line.apply_to == "Account" and line.account == account:
			matches.append(line)
	return matches


def _sort_for_application(lines):
	def key(line):
		is_override = 1 if line.adjustment_type == "Absolute Override" else 0
		specificity = -SPECIFICITY.get(line.apply_to, 0)
		type_rank = 0 if line.adjustment_type == "Percentage" else 1
		return (is_override, specificity, type_rank)

	return sorted(lines, key=key)


def _apply_lines(amount, lines, month):
	applicable = [ln for ln in lines if ln.period_scope != "Specific Month" or ln.month == month]
	for line in _sort_for_application(applicable):
		if line.adjustment_type == "Percentage":
			amount = amount * (1 + flt(line.adjustment_value) / 100)
		elif line.adjustment_type == "Fixed Amount":
			amount = amount + flt(line.adjustment_value)
		elif line.adjustment_type == "Absolute Override":
			amount = flt(line.adjustment_value)
	return amount


def _build_row(filters, dimension, account, scenarios, lines_by_scenario, baseline_source, budget_map, actual_map, forecast_map, month_bounds):
	row = {"dimension": dimension, "account": account}

	baseline_months = _monthly_baseline(
		baseline_source, dimension, account, filters.fiscal_year, budget_map, actual_map, forecast_map, month_bounds
	)
	actual_months = actual_map.get((dimension, account), {}).get(filters.fiscal_year, {})

	scenario_month_maps = {}
	scenario_lines = {}
	for scenario in scenarios:
		scenario_month_maps[scenario.name] = (
			baseline_months
			if scenario.base_on == baseline_source
			else _monthly_baseline(
				scenario.base_on, dimension, account, filters.fiscal_year, budget_map, actual_map, forecast_map, month_bounds
			)
		)
		scenario_lines[scenario.name] = _matching_lines(
			lines_by_scenario.get(scenario.name, []), filters.budget_against, dimension, account
		)

	totals = {"baseline": 0.0}
	scenario_totals = {s.name: 0.0 for s in scenarios}

	for months, (from_date, to_date) in zip(
		get_period_month_ranges_for(filters.period, filters.fiscal_year), get_period_ranges(filters.period, filters.fiscal_year)
	):
		suffix = "" if filters.period == "Yearly" else f" ({formatdate(from_date, 'MMM')})"

		period_baseline = sum(flt(baseline_months.get(m, 0)) for m in months)
		row[frappe.scrub(f"baseline{suffix}")] = period_baseline
		totals["baseline"] += period_baseline

		if filters.get("show_actual", 1):
			period_actual = sum(flt(actual_months.get(m, 0)) for m in months)
			row[frappe.scrub(f"actual_ytd{suffix}")] = period_actual

		for scenario in scenarios:
			scenario_months = scenario_month_maps[scenario.name]
			lines = scenario_lines[scenario.name]

			period_scenario_baseline = sum(flt(scenario_months.get(m, 0)) for m in months)
			period_adjusted = sum(_apply_lines(flt(scenario_months.get(m, 0)), lines, m) for m in months)
			period_adjustment = period_adjusted - period_scenario_baseline

			prefix = scenario.scenario_name
			row[frappe.scrub(f"{prefix}_adjustment{suffix}")] = period_adjustment
			row[frappe.scrub(f"{prefix}_budget{suffix}")] = period_adjusted
			row[frappe.scrub(f"{prefix}_delta_percent{suffix}")] = (
				(period_adjustment / period_scenario_baseline * 100) if period_scenario_baseline else 0
			)

			scenario_totals[scenario.name] += period_adjusted

	if filters.period != "Yearly":
		row["baseline_total"] = totals["baseline"]
		for scenario in scenarios:
			row[frappe.scrub(f"{scenario.scenario_name}_total")] = scenario_totals[scenario.name]

	return row


def get_message(filters, warning):
	parts = [
		_("Scenario adjustments are applied most-specific-first (Cost Center/Project + Account, then Account, then Cost Center/Project, then All); Absolute Override always applies last."),
		_("Actual (Annualised) baselines spread the annualised total evenly across 12 months for period grouping — treat month-level detail on that basis as indicative only."),
	]
	if warning:
		parts.insert(0, warning)
	return "<br>".join(parts)
