import frappe
from frappe.permissions import setup_custom_perms

GRANTS = [
	("Sales Order", "Accounts Manager", {"read": 1, "write": 1, "create": 1, "print": 1, "email": 1}),
	("Item", "Accounts Manager", {"read": 1}),
]


def execute():
	"""Standard ERPNext grants Sales Order and Item read only to Accounts User, not
	Accounts Manager, so users with just the Accounts Manager role (e.g.
	accountsmanager@test.com) could not see the Sales Order list, and even after gaining
	Sales Order access could not fetch Item values onto a Sales Order row (Item read is
	required to pull item fields). Give Accounts Manager read/write/create/print/email on
	Sales Order and read on Item, matching what Accounts User already has. setup_custom_perms
	clones the full standard permission set into Custom DocPerm before any row is added or
	edited, so no existing role loses access."""
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
