import frappe
from frappe.permissions import setup_custom_perms

GRANTS = [
	("Customer", "Sales Staff", {"read": 1}),
	("Customer", "Sales Supervisor", {"read": 1}),
	("Customer", "Sales Manager", {"read": 1}),
]


def execute():
	"""Give Sales Staff, Sales Supervisor and Sales Manager read access on Customer,
	since the Quotation/Sales Order Customer field requires it at every step of the
	Selling Price Approval workflow (Draft -> Pending Supervisor -> Pending Manager ->
	Approved). setup_custom_perms clones the full standard permission set into Custom
	DocPerm before any row is added or edited, so no existing role loses access."""
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
