# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate

CHUNK = 1000


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_rows(filters)

	if filters.get("group_by") == "Item and Sales Person":
		return summary_columns(), summarise(rows)
	return detail_columns(), rows


def get_rows(filters):
	"""One row per Sales Invoice item line of submitted, non-return invoices the user may read.

	Invoices come through get_list so company / customer user permissions apply. The sales person is
	the invoice's Sales Person field, else the first row of its Sales Team.
	"""
	if not filters.get("company"):
		frappe.throw(_("Company is required"))

	invoice_filters = {"docstatus": 1, "is_return": 0, "company": filters.company}
	if filters.get("customer"):
		invoice_filters["customer"] = filters.customer
	if filters.get("from_date") and filters.get("to_date"):
		invoice_filters["posting_date"] = ["between", [getdate(filters.from_date), getdate(filters.to_date)]]
	elif filters.get("from_date"):
		invoice_filters["posting_date"] = [">=", getdate(filters.from_date)]
	elif filters.get("to_date"):
		invoice_filters["posting_date"] = ["<=", getdate(filters.to_date)]

	# custom_sales_person is a field added on the live site by hand, not by this app
	has_sales_person_field = frappe.get_meta("Sales Invoice").has_field("custom_sales_person")
	invoice_fields = ["name", "posting_date", "customer", "currency"]
	if has_sales_person_field:
		invoice_fields.append("custom_sales_person")

	invoices = frappe.get_list(
		"Sales Invoice",
		filters=invoice_filters,
		fields=invoice_fields,
		order_by="posting_date desc, name desc",
		limit_page_length=0,
	)
	if not invoices:
		return []

	names = [d.name for d in invoices]
	by_name = {d.name: d for d in invoices}

	item_filters = {}
	if filters.get("item_code"):
		item_filters["item_code"] = filters.item_code
	if filters.get("item_group"):
		item_filters["item_group"] = filters.item_group

	lines = []
	for start in range(0, len(names), CHUNK):
		lines += frappe.get_all(
			"Sales Invoice Item",
			filters={"parent": ["in", names[start : start + CHUNK]], "parenttype": "Sales Invoice", **item_filters},
			fields=[
				"parent",
				"idx",
				"item_code",
				"item_name",
				"qty",
				"uom",
				"conversion_factor",
				"rate",
				"delivery_note",
			],
			order_by="parent, idx",
		)

	team_lead = first_sales_team_member(names)

	rows = []
	for line in lines:
		invoice = by_name[line.parent]
		sales_person = invoice.get("custom_sales_person") or team_lead.get(line.parent)
		if filters.get("sales_person") and sales_person != filters.sales_person:
			continue

		factor = flt(line.conversion_factor) or 1
		rows.append(
			{
				"posting_date": invoice.posting_date,
				"sales_invoice": line.parent,
				"customer": invoice.customer,
				"sales_person": sales_person,
				"item_code": line.item_code,
				"item_name": line.item_name,
				"delivery_note": line.delivery_note,
				"qty": flt(line.qty),
				"stock_qty": flt(line.qty) * factor,
				"uom": line.uom,
				"rate": flt(line.rate),
				"rate_per_stock_uom": flt(line.rate) / factor,
				"currency": invoice.currency,
			}
		)

	rows.sort(key=lambda r: (r["posting_date"], r["sales_invoice"]), reverse=True)
	return rows


def first_sales_team_member(invoice_names):
	members = {}
	for start in range(0, len(invoice_names), CHUNK):
		for row in frappe.get_all(
			"Sales Team",
			filters={"parenttype": "Sales Invoice", "parent": ["in", invoice_names[start : start + CHUNK]]},
			fields=["parent", "sales_person"],
			order_by="parent, idx",
		):
			members.setdefault(row.parent, row.sales_person)
	return members


def summarise(rows):
	"""One row per item, sales person and currency, with the price range and the latest price.

	Rates are per stock UOM so lines sold in different UOMs compare. The average is weighted by
	quantity. Rows arrive newest first, so the first one seen is the latest.
	"""
	groups = {}
	for row in rows:
		key = (row["item_code"], row["sales_person"] or "", row["currency"])
		group = groups.get(key)
		stock_qty = row["stock_qty"]
		if group is None:
			groups[key] = {
				"item_code": row["item_code"],
				"item_name": row["item_name"],
				"sales_person": row["sales_person"],
				"currency": row["currency"],
				"invoices": {row["sales_invoice"]},
				"qty": row["qty"],
				"_stock_qty": stock_qty,
				"_value": row["rate_per_stock_uom"] * stock_qty,
				"min_rate": row["rate_per_stock_uom"],
				"max_rate": row["rate_per_stock_uom"],
				"last_rate": row["rate_per_stock_uom"],
				"last_date": row["posting_date"],
			}
			continue

		group["invoices"].add(row["sales_invoice"])
		group["qty"] += row["qty"]
		group["_stock_qty"] += stock_qty
		group["_value"] += row["rate_per_stock_uom"] * stock_qty
		group["min_rate"] = min(group["min_rate"], row["rate_per_stock_uom"])
		group["max_rate"] = max(group["max_rate"], row["rate_per_stock_uom"])

	data = []
	for group in groups.values():
		group["invoices"] = len(group["invoices"])
		group["avg_rate"] = group["_value"] / group["_stock_qty"] if group["_stock_qty"] else 0
		del group["_stock_qty"], group["_value"]
		data.append(group)

	data.sort(key=lambda g: (g["item_code"] or "", g["sales_person"] or ""))
	return data


def detail_columns():
	return [
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 140},
		{"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 160},
		{"fieldname": "sales_person", "label": _("Sales Person"), "fieldtype": "Link", "options": "Sales Person", "width": 130},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 130},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "delivery_note", "label": _("Delivery Note"), "fieldtype": "Link", "options": "Delivery Note", "width": 140},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 80},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 70},
		{"fieldname": "rate", "label": _("Rate"), "fieldtype": "Currency", "options": "currency", "width": 100},
		{"fieldname": "rate_per_stock_uom", "label": _("Rate / Stock UOM"), "fieldtype": "Currency", "options": "currency", "width": 120},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 80},
	]


def summary_columns():
	return [
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 130},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "sales_person", "label": _("Sales Person"), "fieldtype": "Link", "options": "Sales Person", "width": 130},
		{"fieldname": "invoices", "label": _("Invoices"), "fieldtype": "Int", "width": 80},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 80},
		{"fieldname": "min_rate", "label": _("Lowest Rate"), "fieldtype": "Currency", "options": "currency", "width": 110},
		{"fieldname": "avg_rate", "label": _("Average Rate"), "fieldtype": "Currency", "options": "currency", "width": 110},
		{"fieldname": "max_rate", "label": _("Highest Rate"), "fieldtype": "Currency", "options": "currency", "width": 110},
		{"fieldname": "last_rate", "label": _("Latest Rate"), "fieldtype": "Currency", "options": "currency", "width": 110},
		{"fieldname": "last_date", "label": _("Latest Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 80},
	]
