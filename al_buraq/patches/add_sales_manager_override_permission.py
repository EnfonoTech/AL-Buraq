import frappe
from frappe.permissions import setup_custom_perms


def execute():
	"""MAS-05: grant permlevel-1 read/write on custom_manager_override to Sales Manager
	on Sales Order and Sales Invoice, without touching either doctype's other role
	permissions (setup_custom_perms clones the full standard permission set into
	Custom DocPerm before we add the new row, so no existing role loses access)."""
	for doctype in ("Sales Order", "Sales Invoice"):
		if not frappe.db.exists("DocType", doctype):
			continue

		setup_custom_perms(doctype)

		if frappe.db.exists(
			"Custom DocPerm",
			{"parent": doctype, "role": "Sales Manager", "permlevel": 1, "if_owner": 0},
		):
			continue

		frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": doctype,
				"parenttype": "DocType",
				"parentfield": "permissions",
				"role": "Sales Manager",
				"permlevel": 1,
				"read": 1,
				"write": 1,
			}
		).insert(ignore_permissions=True)
