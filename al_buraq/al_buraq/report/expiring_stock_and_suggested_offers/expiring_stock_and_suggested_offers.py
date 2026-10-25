# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

from frappe import _
from frappe.utils import cint

from al_buraq.utils.expiry_offers import expiring_batches


def execute(filters=None):
	filters = filters or {}
	within_days = filters.get("within_days")
	rows = expiring_batches(
		within_days=cint(within_days) if within_days not in (None, "") else None,
		item_group=filters.get("item_group"),
	)
	for row in rows:
		row["create_offer"] = _("Create offer") if row["suggested_discount"] is not None else None
	return columns(), rows


def columns():
	return [
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 130},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "batch", "label": _("Batch"), "fieldtype": "Link", "options": "Batch", "width": 130},
		{"fieldname": "qty", "label": _("Qty in Stock"), "fieldtype": "Float", "width": 100},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 70},
		{"fieldname": "expiry_date", "label": _("Expires On"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days_left", "label": _("Days Left"), "fieldtype": "Int", "width": 80},
		{"fieldname": "suggested_discount", "label": _("Suggested Discount %"), "fieldtype": "Percent", "width": 150},
		{"fieldname": "selling_rate", "label": _("Selling Rate"), "fieldtype": "Currency", "width": 100},
		{"fieldname": "offer_rate", "label": _("Offer Rate"), "fieldtype": "Currency", "width": 100},
		{"fieldname": "create_offer", "label": _("Draft Offer"), "fieldtype": "Data", "width": 110},
	]
