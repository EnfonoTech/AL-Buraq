import frappe
from frappe.utils import today

SKIP_USERS = ("Administrator", "Guest")


def users_with_role(role):
	"""Enabled users holding a role, without the built-in Administrator and Guest."""
	if not role:
		return []
	holders = [u for u in frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent") if u not in SKIP_USERS]
	if not holders:
		return []
	return frappe.get_all(
		"User", filters={"name": ["in", holders], "enabled": 1, "user_type": "System User"}, pluck="name"
	)


def notify_users(users, subject, link=None, body=None):
	"""Tell each user once a day, in the system's notification bell. Returns who was told.

	The log is of type Alert, which Frappe never turns into an email, so nothing is queued for a
	mailbox that is set up later. Email is only sent when Al Buraq Settings asks for it and an
	outgoing account exists. Asking again the same day with the same subject does nothing.
	"""
	told = []
	for user in dict.fromkeys(u for u in users if u and u not in SKIP_USERS):
		if frappe.db.exists("Notification Log", {"for_user": user, "subject": subject, "creation": [">=", today()]}):
			continue
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"from_user": "Administrator",
				"type": "Alert",
				"subject": subject,
				"email_content": body,
				"link": link,
			}
		).insert(ignore_permissions=True)
		told.append(user)

	if told and frappe.get_cached_doc("Al Buraq Settings").also_email:
		_send_email(told, subject, body or subject)
	return told


def has_outgoing_account():
	return bool(frappe.db.exists("Email Account", {"enable_outgoing": 1}))


def _send_email(users, subject, message):
	if not has_outgoing_account():
		return
	emails = frappe.get_all("User", filters={"name": ["in", users]}, pluck="email")
	if emails:
		frappe.sendmail(recipients=emails, subject=subject, message=message, delayed=True)
