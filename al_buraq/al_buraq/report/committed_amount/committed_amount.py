# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from al_buraq.utils.budget_common import (
	get_dimension_config,
	get_dimension_rollup,
	get_leaf_expense_accounts,
	get_mr_committed_rows,
	get_po_committed_rows,
)


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
	filters.setdefault("commitment_basis", "Expected Date")
	filters.setdefault("include_material_requests", 1)
	filters.setdefault("only_expense_accounts", 1)
	get_dimension_config(filters.budget_against)  # raises for unsupported values


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
		{"label": _("Account Name"), "fieldname": "account_name", "fieldtype": "Data", "width": 160},
	]

	if filters.get("show_details"):
		columns += [
			{"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 120},
			{
				"label": _("Voucher No"),
				"fieldname": "voucher_no",
				"fieldtype": "Dynamic Link",
				"options": "voucher_type",
				"width": 140,
			},
			{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 100},
			{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
			{"label": _("Pending Qty"), "fieldname": "pending_qty", "fieldtype": "Float", "width": 100},
			{"label": _("Committed Amount"), "fieldname": "committed_amount", "fieldtype": "Currency", "width": 140},
		]
	else:
		columns += [
			{"label": _("PO Committed"), "fieldname": "po_committed", "fieldtype": "Currency", "width": 140},
			{"label": _("MR Committed"), "fieldname": "mr_committed", "fieldtype": "Currency", "width": 140},
			{"label": _("Total Committed"), "fieldname": "total_committed", "fieldtype": "Currency", "width": 140},
		]

	return columns


def get_data(filters):
	dim = get_dimension_config(filters.budget_against)
	dim_field = dim.field
	year_start, year_end = frappe.get_cached_value(
		"Fiscal Year", filters.fiscal_year, ["year_start_date", "year_end_date"]
	)

	rollup = get_dimension_rollup(filters.budget_against, filters.company)
	expense_accounts = (
		set(get_leaf_expense_accounts(filters.company)) if filters.only_expense_accounts else None
	)

	po_rows = get_po_committed_rows(filters, dim_field, year_start, year_end)
	mr_rows = get_mr_committed_rows(filters, dim_field, year_start, year_end) if filters.include_material_requests else []

	rows = [r for r in (po_rows + mr_rows) if not expense_accounts or r.account in expense_accounts]

	account_names = _get_account_names({r.account for r in rows})

	if filters.get("show_details"):
		return _build_detail_rows(rows, rollup, account_names)
	return _build_summary_rows(rows, rollup, account_names)


def _build_detail_rows(rows, rollup, account_names):
	data = []
	for row in rows:
		for dimension in rollup.get(row.dimension, [row.dimension]):
			data.append(
				{
					"dimension": dimension,
					"account": row.account,
					"account_name": account_names.get(row.account),
					"voucher_type": row.voucher_type,
					"voucher_no": row.voucher_no,
					"date": row.date,
					"item_code": row.item_code,
					"pending_qty": flt(row.pending_qty),
					"committed_amount": flt(row.amount),
				}
			)
	return sorted(data, key=lambda r: (r["dimension"], r["account"], r["date"] or ""))


def _build_summary_rows(rows, rollup, account_names):
	summary = {}
	for row in rows:
		leg = "po_committed" if row.voucher_type == "Purchase Order" else "mr_committed"
		for dimension in rollup.get(row.dimension, [row.dimension]):
			key = (dimension, row.account)
			bucket = summary.setdefault(key, {"po_committed": 0.0, "mr_committed": 0.0})
			bucket[leg] = flt(bucket[leg]) + flt(row.amount)

	data = []
	for (dimension, account), amounts in summary.items():
		total = flt(amounts["po_committed"]) + flt(amounts["mr_committed"])
		if not total:
			continue
		data.append(
			{
				"dimension": dimension,
				"account": account,
				"account_name": account_names.get(account),
				"po_committed": amounts["po_committed"],
				"mr_committed": amounts["mr_committed"],
				"total_committed": total,
			}
		)
	return sorted(data, key=lambda r: (r["dimension"], r["account"]))


def _get_account_names(accounts):
	if not accounts:
		return {}
	rows = frappe.get_all("Account", filters={"name": ["in", list(accounts)]}, fields=["name", "account_name"])
	return {r.name: r.account_name for r in rows}


def get_message(filters):
	parts = [
		_("Committed = (PO Amount − PO Billed Amount) for open Purchase Orders, plus the pending portion of open Material Requests."),
		_("'On Hold' Purchase Orders are included — they remain an obligation until cancelled or closed."),
	]
	if filters.only_expense_accounts:
		parts.append(
			_(
				"Only Expense accounts are shown — stock item commitments are excluded because Purchase Receipts post to the warehouse account, not the PO's expense account, so they would never reconcile against Actual."
			)
		)
	return "<br>".join(parts)
