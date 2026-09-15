import frappe
from frappe import _
from frappe.utils import nowdate, add_days, flt


@frappe.whitelist()
def create_material_request(item_code, from_warehouse, to_warehouse, qty, schedule_date, material_request_type, company):
	"""Create and submit a Material Transfer request between two warehouses."""
	if not item_code:
		frappe.throw(_("Item Code is required"))
	if not from_warehouse:
		frappe.throw(_("From Warehouse is required"))
	if not to_warehouse:
		frappe.throw(_("To Warehouse is required"))
	if from_warehouse == to_warehouse:
		frappe.throw(_("From Warehouse and To Warehouse cannot be the same"))
	if not qty or flt(qty) <= 0:
		frappe.throw(_("Quantity must be greater than 0"))
	if not company:
		frappe.throw(_("Company is required"))

	if not frappe.db.exists("Item", item_code):
		frappe.throw(_("Item {0} does not exist").format(item_code))
	if not frappe.db.exists("Warehouse", from_warehouse):
		frappe.throw(_("From Warehouse {0} does not exist").format(from_warehouse))
	if not frappe.db.exists("Warehouse", to_warehouse):
		frappe.throw(_("To Warehouse {0} does not exist").format(to_warehouse))

	item_doc = frappe.get_cached_doc("Item", item_code)

	mr = frappe.new_doc("Material Request")
	mr.transaction_date = nowdate()
	mr.company = company
	mr.material_request_type = "Material Transfer"
	mr.set_warehouse = to_warehouse
	mr.set_from_warehouse = from_warehouse

	mr.append("items", {
		"item_code": item_code,
		"item_name": item_doc.item_name,
		"description": item_doc.description,
		"qty": flt(qty),
		"uom": item_doc.stock_uom,
		"stock_uom": item_doc.stock_uom,
		"schedule_date": schedule_date or add_days(nowdate(), 7),
		"warehouse": to_warehouse,
		"from_warehouse": from_warehouse,
		"item_group": item_doc.item_group,
		"brand": item_doc.brand,
	})

	mr.set_missing_values()
	mr.insert(ignore_permissions=True)
	mr.submit()

	return mr.name
