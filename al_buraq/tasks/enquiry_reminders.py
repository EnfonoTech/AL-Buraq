import json
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import add_days, cint, today

from al_buraq.utils.notify import notify_users, users_with_role

OPEN_STATUSES = ["Open", "Replied"]
MAX_LISTED = 50


def send_unconverted_enquiry_reminders():
	"""Daily (requirement 2.3.3): enquiries with no Job after N days are reported to their owner and
	to the owner's superior. One message per person, listing every enquiry that is due."""
	settings = frappe.get_cached_doc("Al Buraq Settings")
	days = cint(settings.enquiry_reminder_days)
	if days <= 0:
		return {}

	opportunities = unconverted_enquiries(days)
	by_user = {}
	for opp in opportunities:
		for user in {opp.owner, *superiors_of(opp.owner, settings.enquiry_reminder_role)}:
			by_user.setdefault(user, []).append(opp.name)

	for user, names in by_user.items():
		subject = _("{0} enquiries have had no Job for more than {1} days").format(len(names), days)
		link = "/app/opportunity?name=" + quote(json.dumps(["in", names[:MAX_LISTED]]))
		notify_users([user], subject, link=link, body=", ".join(names[:MAX_LISTED]))
	return by_user


def unconverted_enquiries(days):
	"""Open enquiries created at least `days` days ago that no live Job Record points at."""
	opportunities = frappe.get_all(
		"Opportunity",
		filters={"status": ["in", OPEN_STATUSES], "creation": ["<", add_days(today(), 1 - days)]},
		fields=["name", "owner"],
	)
	if not opportunities:
		return []

	with_job = set(
		frappe.get_all(
			"Job Record",
			filters={"opportunity": ["in", [o.name for o in opportunities]], "docstatus": ["<", 2]},
			pluck="opportunity",
		)
	)
	return [o for o in opportunities if o.name not in with_job]


def superiors_of(user, fallback_role):
	"""The owner's superior: Reports To of their Employee record, as a user. Without one, everyone
	holding the fallback role."""
	reports_to = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "reports_to")
	superior = frappe.db.get_value("Employee", reports_to, "user_id") if reports_to else None
	return [superior] if superior else users_with_role(fallback_role)
