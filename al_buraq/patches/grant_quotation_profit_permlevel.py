import frappe
from frappe.permissions import setup_custom_perms

from al_buraq.setup import PROFIT_PERMLEVEL

PROFIT_READ_ROLES = ("Sales Manager", "Sales Supervisor", "Accounts Manager", "System Manager")


def execute():
	"""The Quotation profit block (custom_total_profit, custom_profit_percent, custom_profit_note)
	sits on permlevel 2, so only the roles below can see the margin on a quotation; Sales Users
	preparing the quote cannot. setup_custom_perms clones the standard Quotation permissions into
	Custom DocPerm before the new rows are added, so no existing role loses access at permlevel 0.
	Adjust the role list on the site (Role Permissions Manager) if Al Buraq wants a different group."""
	doctype = "Quotation"
	roles = [r for r in PROFIT_READ_ROLES if frappe.db.exists("Role", r)]
	if not frappe.db.exists("DocType", doctype) or not roles:
		return

	setup_custom_perms(doctype)

	for role in roles:
		if frappe.db.exists(
			"Custom DocPerm",
			{"parent": doctype, "role": role, "permlevel": PROFIT_PERMLEVEL, "if_owner": 0},
		):
			continue

		frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": doctype,
				"parenttype": "DocType",
				"parentfield": "permissions",
				"role": role,
				"permlevel": PROFIT_PERMLEVEL,
				"read": 1,
			}
		).insert(ignore_permissions=True)
