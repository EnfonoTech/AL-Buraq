import frappe
from frappe import _
from frappe.utils import flt


def validate_item_max_selling_rate(doc, method=None):
	"""Item: Maximum Selling Rate must be positive and not below Standard Selling Rate (3.1.3)."""
	max_rate = flt(doc.get("custom_max_selling_rate"))
	if not max_rate:
		return

	if max_rate < 0:
		frappe.throw(_("Maximum Selling Rate cannot be negative."))

	if flt(doc.standard_rate) > max_rate:
		frappe.throw(
			_("Standard Selling Rate {0} cannot be higher than the Maximum Selling Rate {1}.").format(
				frappe.bold(doc.standard_rate), frappe.bold(max_rate)
			)
		)


def validate_item_price_max_selling_rate(doc, method=None):
	"""Item Price: a selling price may not exceed the item's Maximum Selling Rate (3.1.3).

	The maximum is held per stock UOM, so a price quoted in another UOM is converted first. If
	the UOM has no conversion on the item the price is left alone rather than guessed at.
	"""
	if not doc.selling or not doc.item_code:
		return

	item = frappe.db.get_value(
		"Item", doc.item_code, ["custom_max_selling_rate", "stock_uom"], as_dict=True
	)
	if not item or not flt(item.custom_max_selling_rate):
		return

	factor = 1.0
	if doc.uom and doc.uom != item.stock_uom:
		factor = flt(
			frappe.db.get_value(
				"UOM Conversion Detail", {"parent": doc.item_code, "uom": doc.uom}, "conversion_factor"
			)
		)
		if not factor:
			return

	rate_per_stock_uom = flt(doc.price_list_rate) / factor
	if rate_per_stock_uom > flt(item.custom_max_selling_rate):
		frappe.throw(
			_("Selling price {0} for {1} is higher than its Maximum Selling Rate {2}.").format(
				frappe.bold(doc.price_list_rate),
				frappe.bold(doc.item_code),
				frappe.bold(item.custom_max_selling_rate),
			)
		)
