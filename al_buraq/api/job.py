import frappe
from frappe import _
from frappe.utils import nowdate


@frappe.whitelist()
def make_job_from_opportunity(opportunity):
	"""Turn an enquiry (Opportunity) into a Job Record (requirement 2.3.1).

	The Job starts with the departments listed under Default Job Stages in Al Buraq Settings. Asking
	again for an enquiry that already has a live Job returns that Job instead of making a second.
	"""
	opp = frappe.get_doc("Opportunity", opportunity)
	opp.check_permission("read")
	if not frappe.has_permission("Job Record", "create"):
		frappe.throw(_("Not permitted to create Jobs"), frappe.PermissionError)

	existing = frappe.db.get_value("Job Record", {"opportunity": opportunity, "docstatus": ["<", 2]}, "name")
	if existing:
		return {"name": existing, "created": 0}

	job = frappe.new_doc("Job Record")
	job.update(
		{
			"job_name": opp.get("title") or opp.get("customer_name") or opp.name,
			"customer": _customer_of(opp),
			"opportunity": opp.name,
			"date": nowdate(),
		}
	)
	for row in frappe.get_cached_doc("Al Buraq Settings").get("default_stages") or []:
		job.append("stages", {"department": row.department})
	job.insert()

	return {"name": job.name, "created": 1}


def _customer_of(opp):
	"""The Customer behind an enquiry: the party itself, or the customer a Lead became."""
	if opp.opportunity_from == "Customer":
		return opp.party_name
	if opp.opportunity_from == "Lead":
		return frappe.db.get_value("Customer", {"lead_name": opp.party_name}, "name")
	return None
