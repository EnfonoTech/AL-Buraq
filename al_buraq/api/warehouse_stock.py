import frappe
from frappe import _


@frappe.whitelist()
def get_item_warehouse_stock(item_code, company=None, limit=None, target_warehouse=None):
	"""
	Get stock balance for an item across all warehouses in a company.
	Uses Bin table for fast bulk queries.
	"""
	if not item_code:
		frappe.throw(_("Item Code is required"))

	if not company:
		company = frappe.defaults.get_user_default("company")

	if not company:
		frappe.throw(_("Please set a default company"))

	warehouses = frappe.get_all(
		"Warehouse",
		filters={"company": company, "is_group": 0, "disabled": 0},
		fields=["name", "warehouse_name"],
		order_by="name",
	)

	if not warehouses:
		return []

	warehouse_names = [w.name for w in warehouses]
	stock_uom = frappe.db.get_value("Item", item_code, "stock_uom") or ""

	bin_data = frappe.db.sql(
		"""
		SELECT warehouse, actual_qty
		FROM `tabBin`
		WHERE item_code = %s AND warehouse IN %s
		""",
		(item_code, warehouse_names),
		as_dict=True,
	)

	bin_dict = {d.warehouse: (d.actual_qty or 0.0) for d in bin_data}

	stock_data = []
	for warehouse in warehouses:
		stock_qty = bin_dict.get(warehouse.name, 0.0)
		stock_data.append({
			"warehouse": warehouse.name,
			"warehouse_name": warehouse.warehouse_name or warehouse.name,
			"stock_qty": stock_qty,
			"uom": stock_uom,
		})

	if target_warehouse:
		filtered = [r for r in stock_data if r["stock_qty"] > 0 or r["warehouse"] == target_warehouse]
		filtered.sort(key=lambda x: (-1 if x["warehouse"] == target_warehouse else 0, -x["stock_qty"]))
	else:
		filtered = [r for r in stock_data if r["stock_qty"] > 0]
		filtered.sort(key=lambda x: x["stock_qty"], reverse=True)

	if limit:
		return filtered[:int(limit)]

	return filtered


@frappe.whitelist()
def get_available_qty(item_code: str, warehouse: str) -> float:
	"""Return actual_qty from Bin for the given item + warehouse."""
	if not item_code or not warehouse:
		return 0.0
	return frappe.utils.flt(
		frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty") or 0
	)
