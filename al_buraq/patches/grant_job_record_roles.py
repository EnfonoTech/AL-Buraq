import json

import frappe

FLAGS = ("read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export", "share", "print", "email")


def execute():
	"""Job Record now ships with permissions for the sales roles (requirement 2.3). The live site
	created the DocType by hand and gave it its own Custom DocPerm row, and when a DocType has any
	Custom DocPerm rows Frappe ignores the permissions in the app's file. So the shipped rows are
	added there too. A site without Custom DocPerm rows needs nothing: the file is used as it is."""
	if not frappe.db.exists("Custom DocPerm", {"parent": "Job Record"}):
		return

	path = frappe.get_app_path("al_buraq", "al_buraq", "doctype", "job_record", "job_record.json")
	with open(path) as f:
		shipped = json.load(f)["permissions"]

	for perm in shipped:
		permlevel = perm.get("permlevel", 0)
		if not frappe.db.exists("Role", perm["role"]):
			continue
		if frappe.db.exists(
			"Custom DocPerm", {"parent": "Job Record", "role": perm["role"], "permlevel": permlevel, "if_owner": 0}
		):
			continue

		frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": "Job Record",
				"parenttype": "DocType",
				"parentfield": "permissions",
				"role": perm["role"],
				"permlevel": permlevel,
				**{flag: perm[flag] for flag in FLAGS if flag in perm},
			}
		).insert(ignore_permissions=True)

	frappe.clear_cache(doctype="Job Record")
