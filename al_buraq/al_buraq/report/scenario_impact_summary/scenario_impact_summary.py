# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

"""
Scenario Impact Summary — the company-level what-if view: Revenue, COGS,
Expenses, Gross Margin % and Net Cash Position, Base Case vs up to two
named Budget Scenarios.

Calculation-only, like every other report in this suite: it reads Budget,
GL Entry and (via the Cash Forecast report) Payment Schedule/orders/
recurring commitments, applies each Scenario's lines in memory, and writes
nothing back to Budget, GL Entry or Cash Forecast Entry.

Base Case is always the plain company Budget for the Fiscal Year — mixing
different scenarios' own Base On values into one company-wide comparison
would not be apples-to-apples, so Budget is the fixed common denominator
here (unlike Budget Scenario Comparison, which is deliberately per-row and
lets each scenario carry its own baseline).
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, nowdate

from al_buraq.al_buraq.report.budget_scenario_comparison.budget_scenario_comparison import (
	_apply_lines,
	_get_scenario_lines,
	_matching_lines,
)
from al_buraq.al_buraq.report.cash_forecast.cash_forecast import execute as run_cash_forecast
from al_buraq.utils.budget_common import get_budget_map

BUDGET_AGAINST = "Cost Center"  # fixed — Cash Forecast scenario overlay only understands Cost Center
METRICS = ["Revenue", "COGS", "Expenses", "Gross Margin %", "Net Cash Position"]
CHART_METRICS = {"Revenue", "COGS", "Expenses"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	scenarios = _get_scenarios(filters)
	columns = get_columns(scenarios)
	data = get_data(filters, scenarios)
	chart = get_chart_data(scenarios, data)
	message = get_message(filters, scenarios)

	return columns, data, message, chart


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))
	if not filters.get("fiscal_year"):
		frappe.throw(_("Fiscal Year is mandatory"))
	filters.setdefault("cash_horizon_days", 90)


def _get_scenarios(filters):
	names = [n for n in (filters.get("scenario_1"), filters.get("scenario_2")) if n]
	if not names:
		return []

	rows = frappe.get_all(
		"Budget Scenario",
		filters={"name": ["in", names], "company": filters.company, "fiscal_year": filters.fiscal_year},
		fields=["name", "scenario_name", "budget_against"],
	)
	by_name = {r.name: r for r in rows}

	scenarios = []
	for name in names:
		scenario = by_name.get(name)
		if not scenario:
			frappe.throw(_("Budget Scenario {0} not found for this Company/Fiscal Year").format(name))
		if scenario.budget_against != BUDGET_AGAINST:
			frappe.throw(_("Budget Scenario {0} must be Cost Center-based to appear here").format(name))
		scenarios.append(scenario)
	return scenarios


def get_columns(scenarios):
	columns = [
		{"label": _("Metric"), "fieldname": "metric", "fieldtype": "Data", "width": 180},
		{"label": _("Base Case"), "fieldname": "base_case", "fieldtype": "Float", "width": 140},
	]
	for i, scenario in enumerate(scenarios, start=1):
		columns += [
			{"label": scenario.scenario_name, "fieldname": f"scenario_{i}", "fieldtype": "Float", "width": 140},
			{
				"label": _("{0} — Δ vs Base").format(scenario.scenario_name),
				"fieldname": f"scenario_{i}_diff",
				"fieldtype": "Float",
				"width": 140,
			},
			{
				"label": _("{0} — Δ% vs Base").format(scenario.scenario_name),
				"fieldname": f"scenario_{i}_diff_percent",
				"fieldtype": "Percent",
				"width": 110,
			},
		]
	return columns


def get_data(filters, scenarios):
	base_filters = frappe._dict(
		company=filters.company,
		budget_against=BUDGET_AGAINST,
		fiscal_year=filters.fiscal_year,
		from_fiscal_year=filters.fiscal_year,
		to_fiscal_year=filters.fiscal_year,
	)
	budget_map = get_budget_map(base_filters)
	classification = _get_account_classification(filters.company)
	lines_by_scenario = _get_scenario_lines([s.name for s in scenarios]) if scenarios else {}

	base_totals = _bucket_totals(filters, budget_map, classification, None)
	base_totals["Gross Margin %"] = _gross_margin(base_totals)
	base_totals["Net Cash Position"] = _get_net_cash_position(filters)

	scenario_totals = {}
	for scenario in scenarios:
		totals = _bucket_totals(filters, budget_map, classification, lines_by_scenario.get(scenario.name, []))
		totals["Gross Margin %"] = _gross_margin(totals)
		totals["Net Cash Position"] = _get_net_cash_position(filters, scenario.name)
		scenario_totals[scenario.name] = totals

	data = []
	for metric in METRICS:
		row = {"metric": _(metric), "base_case": base_totals[metric]}
		for i, scenario in enumerate(scenarios, start=1):
			value = scenario_totals[scenario.name][metric]
			row[f"scenario_{i}"] = value
			row[f"scenario_{i}_diff"] = value - row["base_case"]
			if metric == "Gross Margin %":
				# already a percentage — a "% change of a %" is not meaningful, the point-difference above says it all
				row[f"scenario_{i}_diff_percent"] = None
			else:
				row[f"scenario_{i}_diff_percent"] = (
					(row[f"scenario_{i}_diff"] / row["base_case"] * 100) if row["base_case"] else 0
				)
		data.append(row)

	return data


def _get_account_classification(company):
	"""{account: 'Revenue'|'COGS'|'Expenses'}, leaf Income/Expense accounts."""
	rows = frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0, "root_type": ["in", ["Income", "Expense"]]},
		fields=["name", "root_type", "account_type"],
	)
	classification = {}
	for row in rows:
		if row.root_type == "Income":
			classification[row.name] = "Revenue"
		elif row.account_type == "Cost of Goods Sold":
			classification[row.name] = "COGS"
		else:
			classification[row.name] = "Expenses"
	return classification


def _bucket_totals(filters, budget_map, classification, lines):
	"""{'Revenue': x, 'COGS': y, 'Expenses': z} — every (dimension, account)
	in the Budget, classified and summed; `lines` (a scenario's Percentage/
	Fixed Amount/Absolute Override lines) are applied per Cost Center
	before summing, so a Cost Center-scoped adjustment only moves that
	Cost Center's contribution to the company total."""
	totals = {"Revenue": 0.0, "COGS": 0.0, "Expenses": 0.0}

	for (dimension, account), year_map in budget_map.items():
		bucket = classification.get(account)
		if not bucket:
			continue

		month_map = year_map.get(filters.fiscal_year, {})
		if not lines:
			totals[bucket] += sum(flt(v) for v in month_map.values())
			continue

		matched = _matching_lines(lines, BUDGET_AGAINST, dimension, account)
		if not matched:
			totals[bucket] += sum(flt(v) for v in month_map.values())
			continue

		for month, amount in month_map.items():
			totals[bucket] += _apply_lines(flt(amount), matched, month)

	return totals


def _gross_margin(totals):
	revenue = totals["Revenue"]
	return ((revenue - totals["COGS"]) / revenue * 100) if revenue else 0.0


def _get_net_cash_position(filters, scenario_name=None):
	"""Closing cash position at the end of the cash horizon (default 90
	days out), optionally under a Scenario's Delay in Days overlay —
	delegates straight to the Cash Forecast report so both stay reconciled
	to the same logic."""
	cash_filters = {
		"company": filters.company,
		"from_date": nowdate(),
		"to_date": add_days(nowdate(), cint(filters.cash_horizon_days)),
		"bucket": "Monthly",
		"include_overdue": 1,
		"include_opening_cash": 1,
		"show_details": 0,
	}
	if scenario_name:
		cash_filters["apply_scenario"] = scenario_name

	_columns, buckets, _message, _chart = run_cash_forecast(cash_filters)
	return flt(buckets[-1]["cumulative_cash"]) if buckets else 0.0


def get_chart_data(scenarios, data):
	if not scenarios:
		return None

	chart_rows = [r for r in data if r["metric"] in {_(m) for m in CHART_METRICS}]
	if not chart_rows:
		return None

	datasets = [{"name": _("Base Case"), "values": [r["base_case"] for r in chart_rows]}]
	for i, scenario in enumerate(scenarios, start=1):
		datasets.append({"name": scenario.scenario_name, "values": [r[f"scenario_{i}"] for r in chart_rows]})

	return {
		"data": {"labels": [r["metric"] for r in chart_rows], "datasets": datasets},
		"type": "bar",
		"barOptions": {"stacked": 0},
	}


def get_message(filters, scenarios):
	parts = [
		_("Base Case is always the plain company Budget for the Fiscal Year (Cost Center-based only) — each Scenario applies its Percentage/Fixed Amount/Absolute Override lines on top of that same baseline, so the comparison is apples-to-apples."),
		_("Revenue = Income accounts. COGS = Expense accounts with Account Type 'Cost of Goods Sold'. Expenses = every other Expense account."),
		_("Net Cash Position is the Cash Forecast's closing cash {0} days out from today, including that Scenario's Delay in Days lines where set.").format(
			cint(filters.cash_horizon_days)
		),
		_("Calculation-only: nothing here is written to Budget, GL Entry or Cash Flow Forecast — every number is computed fresh for this report run."),
	]
	if not scenarios:
		parts.insert(0, _("Select Scenario 1 (and optionally Scenario 2) to compare against the Base Case."))
	return "<br>".join(parts)
