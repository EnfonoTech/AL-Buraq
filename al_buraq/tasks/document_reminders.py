import json
from urllib.parse import quote

import frappe
from frappe.utils import add_days, cint, today

from al_buraq.utils.notify import notify_users, users_with_role

MAX_LISTED = 50


def run_document_reminders():
	"""Daily (requirement 1.1): apply every enabled Document Reminder Rule."""
	sent = {}
	for name in frappe.get_all("Document Reminder Rule", filters={"enabled": 1}, pluck="name"):
		try:
			sent[name] = run_rule(frappe.get_doc("Document Reminder Rule", name))
		except Exception:
			frappe.log_error(title=f"Document Reminder Rule {name} failed")
	return sent


def run_rule(rule):
	"""Tell the rule's people about the documents that match today. Returns {user: count}."""
	docs = matching_documents(rule)
	if not docs:
		return {}

	by_user = {}
	for user in users_with_roles(rule):
		by_user[user] = [d.name for d in docs]
	if rule.notify_owner:
		for doc in docs:
			by_user.setdefault(doc.owner, []).append(doc.name)

	for user, names in by_user.items():
		names = list(dict.fromkeys(names))
		by_user[user] = names
		subject = fill_subject(rule, len(names))
		link = f"/app/{frappe.scrub(rule.document_type).replace('_', '-')}?name=" + quote(
			json.dumps(["in", names[:MAX_LISTED]])
		)
		notify_users([user], subject, link=link, body=", ".join(names[:MAX_LISTED]))
	return {user: len(names) for user, names in by_user.items()}


def fill_subject(rule, count):
	"""The rule's message with {count}, {doctype} and {days} replaced; nothing else is interpreted."""
	return (
		rule.subject.replace("{count}", str(count))
		.replace("{doctype}", rule.document_type)
		.replace("{days}", str(cint(rule.days)))
	)


def matching_documents(rule):
	"""Documents whose watched date is due under the rule, and that pass its filters.

	Before: from `days` days before the date until the date. On: the date is today. After: from
	`days` days after the date onwards, until the document stops matching the filters (paid,
	submitted, ...).
	"""
	field, days = rule.date_field, cint(rule.days)
	filters = parse_filters(rule.filters)
	if rule.when == "Before":
		filters += [[field, ">=", today()], [field, "<=", add_days(today(), days)]]
	elif rule.when == "On":
		filters.append([field, "=", today()])
	else:
		filters.append([field, "<=", add_days(today(), -days)])

	return frappe.get_all(rule.document_type, filters=filters, fields=["name", "owner"], limit_page_length=0)


def users_with_roles(rule):
	users = []
	for row in rule.get("roles") or []:
		users += users_with_role(row.role)
	return list(dict.fromkeys(users))


def parse_filters(value):
	"""The rule's filters field as a list of [field, operator, value] rows."""
	if not value or not str(value).strip():
		return []
	rows = json.loads(value)
	if not isinstance(rows, list) or not all(isinstance(r, list) and len(r) in (3, 4) for r in rows):
		raise ValueError("Filters must be a JSON list of [field, operator, value] rows")
	return rows
