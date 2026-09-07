import frappe
from frappe.permissions import setup_custom_perms

GRANTS = [
	("Item", "Store Keeper", {"read": 1, "write": 1, "create": 1}),
	("Item", "Store Manager", {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1}),
	("Stock Entry", "Store Keeper", {"read": 1, "write": 1, "create": 1}),
	("Stock Entry", "Store Manager", {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1}),
	("Customer", "Accounts Staff", {"read": 1, "write": 1, "create": 1}),
	("Customer", "Accounts Manager", {"write": 1}),
	("Shipping Rule", "Sales Staff", {"read": 1, "write": 1, "create": 1}),
	("Shipping Rule", "Sales Supervisor", {"read": 1, "write": 1}),
	("Shipping Rule", "Sales Manager", {"read": 1, "write": 1}),
	("Quotation", "Sales Staff", {"read": 1, "write": 1, "create": 1}),
	("Quotation", "Sales Supervisor", {"read": 1, "write": 1, "submit": 1}),
	("Sales Order", "Sales Staff", {"read": 1, "write": 1, "create": 1}),
	("Sales Order", "Sales Supervisor", {"read": 1, "write": 1, "submit": 1}),
]


def execute():
	"""Grant the base doctype permissions the MAS-03/04/06/08 workflow roles need to
	actually use their target doctypes. allow_edit on a Workflow only restricts editing
	within a state; it does not grant the underlying read/write/create/submit permission,
	so these custom roles (and, for Customer/Shipping Rule, some standard roles too) had
	zero access to the doctypes their own workflow is built on. setup_custom_perms clones
	the full standard permission set into Custom DocPerm before any row is added or edited,
	so no existing role loses access."""
	for doctype, role, ptypes in GRANTS:
		if not frappe.db.exists("DocType", doctype) or not frappe.db.exists("Role", role):
			continue

		setup_custom_perms(doctype)

		existing_name = frappe.db.get_value(
			"Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
		)
		if existing_name:
			doc = frappe.get_doc("Custom DocPerm", existing_name)
			changed = False
			for key, value in ptypes.items():
				if doc.get(key) != value:
					doc.set(key, value)
					changed = True
			if changed:
				doc.save(ignore_permissions=True)
			continue

		frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": doctype,
				"parenttype": "DocType",
				"parentfield": "permissions",
				"role": role,
				"permlevel": 0,
				**ptypes,
			}
		).insert(ignore_permissions=True)
