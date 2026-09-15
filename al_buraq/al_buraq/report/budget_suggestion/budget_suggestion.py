# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

from datetime import timedelta

import frappe
from dateutil.relativedelta import relativedelta
from frappe import _
from frappe.utils import cint, flt, formatdate, getdate

from al_buraq.utils.budget_common import (
	get_budget_map,
	get_dimension_config,
	get_leaf_expense_accounts,
	get_monthly_actual_map,
)

# Data-quality floor: a Cost Center/Account combination needs at least this
# many months of posted GL activity within the history window to get a
# suggestion. Combinations with less are skipped entirely — never
# zero-filled — per the client's explicit data-quality rule.
MIN_HISTORY_MONTHS = 3

METHODS = ("Moving Average", "YoY Growth %")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	window_start, window_end, month_keys = _get_history_window(filters.target_fiscal_year, cint(filters.history_months))

	columns = get_columns(filters)
	data, skipped_count = get_data(filters, month_keys)
	message = get_message(filters, window_start, window_end, skipped_count)

	return columns, data, message


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))
	if not filters.get("target_fiscal_year"):
		frappe.throw(_("Target Fiscal Year is mandatory"))
	if not frappe.db.exists("Fiscal Year", filters.target_fiscal_year):
		frappe.throw(_("{0} is not a valid Fiscal Year").format(filters.target_fiscal_year))
	filters.setdefault("budget_against", "Cost Center")
	filters.setdefault("history_months", 12)
	filters.setdefault("method", "Moving Average")
	filters.setdefault("round_to_nearest", 100)
	filters.setdefault("min_amount", 0)
	filters.setdefault("include_unbudgeted_accounts", 1)

	if not (MIN_HISTORY_MONTHS <= cint(filters.history_months) <= 60):
		frappe.throw(_("History Months must be between {0} and 60").format(MIN_HISTORY_MONTHS))
	if filters.method not in METHODS:
		frappe.throw(_("Unsupported Method: {0}").format(filters.method))
	if filters.method == "YoY Growth %" and cint(filters.history_months) < MIN_HISTORY_MONTHS * 2:
		frappe.throw(_("YoY Growth % needs at least {0} months of history (two comparable halves)").format(MIN_HISTORY_MONTHS * 2))

	get_dimension_config(filters.budget_against)


def _get_history_window(target_fiscal_year, history_months):
	"""The N months immediately before the target Fiscal Year starts —
	always made up of closed, complete months, regardless of when the
	report happens to be run."""
	fy_start = frappe.get_cached_value("Fiscal Year", target_fiscal_year, "year_start_date")
	if not fy_start:
		frappe.throw(_("Fiscal Year {0} not found").format(target_fiscal_year))

	window_end = getdate(fy_start) - timedelta(days=1)
	window_start = getdate(fy_start) - relativedelta(months=history_months)

	month_keys = []
	cursor = window_start.replace(day=1)
	while cursor <= window_end:
		month_keys.append(cursor.strftime("%Y-%m"))
		cursor = cursor + relativedelta(months=1)

	return window_start, window_end, month_keys


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
		{"label": _("Account Name"), "fieldname": "account_name", "fieldtype": "Data", "width": 160},
		{"label": _("Method Used"), "fieldname": "method_used", "fieldtype": "Data", "width": 120},
		{"label": _("History Available"), "fieldname": "history_available", "fieldtype": "Data", "width": 140},
		{
			"label": _("Historical Average / Prior-Year Value"),
			"fieldname": "basis_amount",
			"fieldtype": "Currency",
			"width": 190,
		},
		{"label": _("Growth %"), "fieldname": "growth_percent", "fieldtype": "Percent", "width": 90},
		{"label": _("Suggested Budget"), "fieldname": "suggested_budget", "fieldtype": "Currency", "width": 140},
		{"label": _("Current FY Budget"), "fieldname": "current_budget", "fieldtype": "Currency", "width": 140},
		{"label": _("Change vs Current"), "fieldname": "change_amount", "fieldtype": "Currency", "width": 140},
		{"label": _("Change %"), "fieldname": "change_percent", "fieldtype": "Percent", "width": 90},
	]


def get_data(filters, month_keys):
	accounts = get_leaf_expense_accounts(filters.company, root_types=["Expense", "Income"])
	if filters.get("account"):
		accounts = [a for a in accounts if a in set(filters.account)]

	window_start = f"{month_keys[0]}-01" if month_keys else None
	window_end = _month_end(month_keys[-1]) if month_keys else None

	actual_filters = frappe._dict(
		company=filters.company,
		budget_against=filters.budget_against,
		from_date=window_start,
		to_date=window_end,
	)
	monthly_actual_map = get_monthly_actual_map(actual_filters, accounts)

	current_budget_filters = frappe._dict(
		company=filters.company,
		budget_against=filters.budget_against,
		from_fiscal_year=filters.target_fiscal_year,
		to_fiscal_year=filters.target_fiscal_year,
		budget_against_filter=filters.get("budget_against_filter"),
		account=filters.get("account"),
	)
	current_budget_map = get_budget_map(current_budget_filters)

	row_keys = set(monthly_actual_map)
	if filters.include_unbudgeted_accounts:
		row_keys |= set(current_budget_map)
	else:
		row_keys &= set(current_budget_map)

	if filters.get("budget_against_filter"):
		row_keys = {k for k in row_keys if k[0] in filters.budget_against_filter}
	if filters.get("account"):
		row_keys = {k for k in row_keys if k[1] in set(filters.account)}

	account_names = _get_account_names({k[1] for k in row_keys})

	data = []
	skipped_count = 0
	for dimension, account in sorted(row_keys):
		month_map = monthly_actual_map.get((dimension, account), {})
		result = _compute_suggestion(month_map, month_keys, filters.method)
		if result is None:
			skipped_count += 1
			continue

		basis_amount, growth_percent, history_available = result
		suggested = _round_to_nearest(basis_amount * (1 + growth_percent / 100), filters.round_to_nearest)

		current_budget_month_map = current_budget_map.get((dimension, account), {}).get(filters.target_fiscal_year, {})
		current_budget = sum(flt(v) for v in current_budget_month_map.values())

		if suggested < flt(filters.min_amount):
			continue

		data.append(
			{
				"dimension": dimension,
				"account": account,
				"account_name": account_names.get(account),
				"method_used": filters.method,
				"history_available": _("{0} of {1} months").format(history_available, len(month_keys)),
				"basis_amount": basis_amount,
				"growth_percent": growth_percent,
				"suggested_budget": suggested,
				"current_budget": current_budget,
				"change_amount": suggested - current_budget,
				"change_percent": ((suggested - current_budget) / current_budget * 100) if current_budget else 0,
			}
		)

	return data, skipped_count


def _compute_suggestion(month_map, month_keys, method):
	"""Returns (basis_amount, growth_percent, history_available_months), or
	None if there isn't enough clean history to suggest anything at all."""
	history_available = len([m for m in month_keys if flt(month_map.get(m, 0))])
	if history_available < MIN_HISTORY_MONTHS:
		return None

	if method == "Moving Average":
		monthly_average = sum(flt(month_map.get(m, 0)) for m in month_keys) / len(month_keys)
		return abs(monthly_average) * 12, 0.0, history_available

	# YoY Growth %: split the window into an older and a newer half, each
	# annualised so windows that aren't exact-year multiples still compare
	# fairly, then project the observed growth one more period forward.
	half = len(month_keys) // 2
	prior_keys, recent_keys = month_keys[:half], month_keys[half:]

	prior_available = len([m for m in prior_keys if flt(month_map.get(m, 0))])
	recent_available = len([m for m in recent_keys if flt(month_map.get(m, 0))])
	if prior_available < MIN_HISTORY_MONTHS or recent_available < MIN_HISTORY_MONTHS:
		return None

	prior_annualised = abs(sum(flt(month_map.get(m, 0)) for m in prior_keys)) * (12 / len(prior_keys))
	recent_annualised = abs(sum(flt(month_map.get(m, 0)) for m in recent_keys)) * (12 / len(recent_keys))

	growth_percent = ((recent_annualised / prior_annualised) - 1) * 100 if prior_annualised else 0.0
	return recent_annualised, growth_percent, history_available


def _round_to_nearest(amount, nearest):
	nearest = flt(nearest) or 1
	return round(amount / nearest) * nearest


def _month_end(month_key):
	year, month = (int(part) for part in month_key.split("-"))
	next_month = getdate(f"{year}-{month:02d}-01") + relativedelta(months=1)
	return next_month - timedelta(days=1)


def _get_account_names(accounts):
	if not accounts:
		return {}
	rows = frappe.get_all("Account", filters={"name": ["in", list(accounts)]}, fields=["name", "account_name"])
	return {r.name: r.account_name for r in rows}


def get_message(filters, window_start, window_end, skipped_count):
	parts = [
		_("History window: {0} to {1} ({2} months), Method: {3}.").format(
			formatdate(window_start), formatdate(window_end), filters.history_months, filters.method
		),
		_("A Cost Center/Account combination needs at least {0} months of posted GL activity within the window to get a suggestion — combinations with less are skipped, never zero-filled.").format(
			MIN_HISTORY_MONTHS
		),
	]
	if filters.method == "YoY Growth %":
		parts.append(
			_("Growth % is the observed change between the older and newer half of the history window (each annualised to be comparable), applied once more to project the target year from the newer half.")
		)
	if skipped_count:
		parts.append(_("{0} Cost Center/Account combination(s) were skipped for insufficient history.").format(skipped_count))
	parts.append(
		_("This is a read-only suggestion. Use 'Create Draft Budgets' to generate draft (unsubmitted) Budget records from these rows as a separate explicit action — nothing here is written automatically.")
	)
	return "<br>".join(parts)
