import frappe
from frappe.permissions import setup_custom_perms


def execute():
	"""custom_approval_status on Customer gates the Customer Credit Limit Approval workflow,
	but at permlevel 0 any role with Customer write access (e.g. Accounts Staff) could set it
	to "Approved" directly via a save that doesn't touch credit_limit/payment_terms, bypassing
	the Reset Approval Status script (which only re-locks it to Pending when one of those two
	fields changes) and the workflow's Accounts-Manager-only Approve/Reject transition. Lock
	the field to permlevel 1 (see the Customer-custom_approval_status Custom Field fixture) and
	grant only Accounts Manager read/write on it, mirroring how custom_manager_override on
	Sales Order/Sales Invoice is restricted to Sales Manager. setup_custom_perms clones the
	full standard permission set into Custom DocPerm before we add the new row, so no existing
	role loses access at permlevel 0."""
	doctype = "Customer"
	role = "Accounts Manager"

	if not frappe.db.exists("DocType", doctype) or not frappe.db.exists("Role", role):
		return

	setup_custom_perms(doctype)

	if frappe.db.exists(
		"Custom DocPerm",
		{"parent": doctype, "role": role, "permlevel": 1, "if_owner": 0},
	):
		return

	frappe.get_doc(
		{
			"doctype": "Custom DocPerm",
			"parent": doctype,
			"parenttype": "DocType",
			"parentfield": "permissions",
			"role": role,
			"permlevel": 1,
			"read": 1,
			"write": 1,
		}
	).insert(ignore_permissions=True)
