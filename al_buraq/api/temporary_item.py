import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils import cint, cstr


@frappe.whitelist()
def create_temporary_item(item_name, item_group, stock_uom, description=None, quotation=None):
	"""Create a temporary Item from a Quotation for a product that is out of stock (2.1.3).

	Sales users cannot create Items, so the insert bypasses Item permissions; the caller must be
	able to edit Quotations. The item is flagged temporary and still goes through the normal item
	approval (it starts as Pending like any new item).
	"""
	if not frappe.has_permission("Quotation", "write"):
		frappe.throw(_("Not permitted to create items from a Quotation"), frappe.PermissionError)

	item_name = cstr(item_name).strip()
	if not item_name:
		frappe.throw(_("Item Name is required"))
	if not frappe.db.exists("Item Group", item_group):
		frappe.throw(_("Item Group {0} does not exist").format(item_group))
	if not frappe.db.exists("UOM", stock_uom):
		frappe.throw(_("UOM {0} does not exist").format(stock_uom))

	doc = frappe.new_doc("Item")
	doc.update(
		{
			"item_name": item_name,
			"item_group": item_group,
			"stock_uom": stock_uom,
			"description": cstr(description).strip() or item_name,
			"is_stock_item": 1,
			"custom_is_temporary": 1,
			"custom_temp_quotation": quotation if quotation and frappe.db.exists("Quotation", quotation) else None,
		}
	)

	if frappe.db.get_default("item_naming_by") == "Naming Series":
		options = cstr(frappe.get_meta("Item").get_field("naming_series").options).split("\n")
		doc.naming_series = next((o for o in options if o), None)
	else:
		doc.item_code = make_autoname("TMP-.#####")

	doc.flags.ignore_permissions = True
	doc.insert()

	return {"item_code": doc.name, "item_name": doc.item_name, "stock_uom": doc.stock_uom}


@frappe.whitelist()
def merge_temporary_item(temporary_item, target_item):
	"""Merge a temporary Item into the real Item once the real one exists (2.1.3).

	Every document that points at the temporary item (quotations, orders, ...) is repointed to
	the target by ERPNext's own Item merge, then the temporary item is deleted. This cannot be
	undone, so it needs Item write and delete rights.
	"""
	if not (frappe.has_permission("Item", "write") and frappe.has_permission("Item", "delete")):
		frappe.throw(_("Not permitted to merge items"), frappe.PermissionError)

	if temporary_item == target_item:
		frappe.throw(_("Choose a different item to merge into"))
	if not frappe.db.exists("Item", temporary_item) or not frappe.db.exists("Item", target_item):
		frappe.throw(_("Item not found"))

	temp = frappe.db.get_value(
		"Item",
		temporary_item,
		["custom_is_temporary", "custom_temp_quotation", "custom_temp_received_on"],
		as_dict=True,
	)
	if not (cint(temp.custom_is_temporary) or temp.custom_temp_quotation or temp.custom_temp_received_on):
		frappe.throw(_("{0} is not a temporary item").format(temporary_item))
	if cint(frappe.db.get_value("Item", target_item, "custom_is_temporary")):
		frappe.throw(_("{0} is itself a temporary item").format(target_item))

	frappe.rename_doc("Item", temporary_item, target_item, merge=True)
	return target_item
