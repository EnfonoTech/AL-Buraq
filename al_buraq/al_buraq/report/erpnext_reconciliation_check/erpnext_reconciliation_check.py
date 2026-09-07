# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

"""
ERPNext Reconciliation Check — Phase 7 (Reconciliation & UAT).

Cross-checks this suite's own GL Entry aggregation against
erpnext.accounts.utils.get_balance_on, the native utility ERPNext itself
uses throughout core (Payment Entry, Journal Entry, Party balances) — a
genuinely independent code path, not a re-run of our own query. If this
report shows all green, the "is the tool even right" question is answered
before UAT starts.

Deliberately narrow: only leaf Cost Centres (get_balance_on matches a
Cost Centre exactly, no tree rollup, so leaf-vs-leaf is the only
apples-to-apples comparison), and only combinations with non-zero Actual
(nothing to reconcile otherwise).
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt

from erpnext.accounts.utils import get_balance_on

from al_buraq.al_buraq.report.cash_forecast.cash_forecast import get_opening_cash
from al_buraq.utils.budget_common import get_actual_map, get_dimension_config, get_leaf_expense_accounts

DEFAULT_TOLERANCE = 0.5


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	columns = get_columns()
	data = _check_actuals(filters) + _check_opening_cash(filters)
	message = get_message(filters, data)

	return columns, data, message


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))
	if not filters.get("fiscal_year"):
		frappe.throw(_("Fiscal Year is mandatory"))
	filters.setdefault("budget_against", "Cost Center")
	filters.setdefault("tolerance", DEFAULT_TOLERANCE)
	get_dimension_config(filters.budget_against)


def get_columns():
	return [
		{"label": _("Check"), "fieldname": "check", "fieldtype": "Data", "width": 220},
		{"label": _("Cost Center"), "fieldname": "dimension", "fieldtype": "Link", "options": "Cost Center", "width": 140},
		{"label": _("Account"), "fieldname": "account", "fieldtype": "Link", "options": "Account", "width": 160},
		{"label": _("Our Value"), "fieldname": "our_value", "fieldtype": "Currency", "width": 130},
		{"label": _("Native ERPNext Value"), "fieldname": "native_value", "fieldtype": "Currency", "width": 150},
		{"label": _("Difference"), "fieldname": "difference", "fieldtype": "Currency", "width": 120},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
	]


def _check_actuals(filters):
	if filters.budget_against != "Cost Center":
		return []  # get_balance_on takes a Cost Center, not a Project — nothing to reconcile against

	leaf_dimensions = frappe.get_all("Cost Center", filters={"company": filters.company, "is_group": 0}, pluck="name")
	if filters.get("budget_against_filter"):
		leaf_dimensions = [d for d in leaf_dimensions if d in set(filters.budget_against_filter)]

	accounts = get_leaf_expense_accounts(filters.company, root_types=["Expense", "Income"])
	if filters.get("account"):
		accounts = [a for a in accounts if a in set(filters.account)]

	base_filters = frappe._dict(
		company=filters.company,
		budget_against="Cost Center",
		from_fiscal_year=filters.fiscal_year,
		to_fiscal_year=filters.fiscal_year,
	)
	actual_map = get_actual_map(base_filters, accounts)

	fy_start, fy_end = frappe.get_cached_value("Fiscal Year", filters.fiscal_year, ["year_start_date", "year_end_date"])
	day_before_start = add_days(fy_start, -1)

	rows = []
	for dimension in leaf_dimensions:
		for account in accounts:
			our_value = sum(flt(v) for v in actual_map.get((dimension, account), {}).get(filters.fiscal_year, {}).values())
			if not our_value:
				continue

			native_end = get_balance_on(account=account, date=fy_end, cost_center=dimension, company=filters.company)
			native_start = get_balance_on(account=account, date=day_before_start, cost_center=dimension, company=filters.company)
			native_value = flt(native_end) - flt(native_start)

			rows.append(_make_row(_("Actual (native get_balance_on)"), dimension, account, our_value, native_value, filters))

	return rows


def _check_opening_cash(filters):
	fy_start = frappe.get_cached_value("Fiscal Year", filters.fiscal_year, "year_start_date")

	our_value = get_opening_cash(frappe._dict(company=filters.company, from_date=fy_start))

	accounts = frappe.get_all(
		"Account",
		filters={"company": filters.company, "account_type": ["in", ["Bank", "Cash"]], "is_group": 0},
		pluck="name",
	)
	native_value = sum(
		flt(get_balance_on(account=account, date=add_days(fy_start, -1), company=filters.company)) for account in accounts
	)

	return [
		_make_row(
			_("Opening Cash at Fiscal Year Start (native get_balance_on)"),
			filters.company,
			_("All Bank/Cash Accounts"),
			our_value,
			native_value,
			filters,
		)
	]


def _make_row(check, dimension, account, our_value, native_value, filters):
	difference = our_value - native_value
	return {
		"check": check,
		"dimension": dimension,
		"account": account,
		"our_value": our_value,
		"native_value": native_value,
		"difference": difference,
		"status": _("OK") if abs(difference) <= flt(filters.tolerance) else _("MISMATCH"),
	}


def get_message(filters, data):
	mismatches = [r for r in data if r["status"] == _("MISMATCH")]
	parts = [
		_("Cross-checks this suite's own GL Entry aggregation against ERPNext's native accounts.utils.get_balance_on for the same Company/Fiscal Year — a genuinely independent code path, not a re-run of our own query."),
		_("Only leaf Cost Centres and combinations with non-zero Actual are checked."),
		_("Calls get_balance_on once per Cost Centre/Account combination — fine for periodic Phase 7 reconciliation, not meant for frequent/automatic runs on large datasets."),
	]
	if mismatches:
		parts.append(_("<b>{0} mismatch(es) found</b> — investigate before relying on the affected figures.").format(len(mismatches)))
	else:
		parts.append(_("<b>All checks passed</b> within tolerance of {0}.").format(flt(filters.tolerance)))
	return "<br>".join(parts)
