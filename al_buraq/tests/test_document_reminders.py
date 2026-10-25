from unittest.mock import patch

import frappe
from frappe.utils import add_days, nowdate

from al_buraq.patches import seed_batch3_defaults
from al_buraq.tasks.document_reminders import fill_subject, matching_documents, run_document_reminders, run_rule
from al_buraq.tests.test_job_tracking import set_settings
from al_buraq.tests.utils import AlBuraqTestCase, bells, ensure_company, make_user
from al_buraq.utils import notify


def make_todo(days_from_today, status="Open", owner="Administrator"):
	todo = frappe.get_doc(
		{"doctype": "ToDo", "description": "AB reminder test", "date": add_days(nowdate(), days_from_today), "status": status}
	)
	todo.insert(ignore_permissions=True)
	frappe.db.set_value("ToDo", todo.name, "owner", owner, update_modified=False)
	return todo


def make_rule(name="AB todo rule", **kwargs):
	if frappe.db.exists("Document Reminder Rule", name):
		frappe.delete_doc("Document Reminder Rule", name, force=True)
	values = {
		"doctype": "Document Reminder Rule",
		"rule_name": name,
		"document_type": "ToDo",
		"date_field": "date",
		"when": "Before",
		"days": 2,
		"filters": '[["status", "=", "Open"]]',
		"subject": "{count} {doctype} due within {days} days",
		"roles": [{"role": "Sales Manager"}],
		"enabled": 1,
	}
	values.update(kwargs)
	rule = frappe.get_doc(values)
	rule.insert(ignore_permissions=True)
	return rule


class TestDocumentReminders(AlBuraqTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_company()
		cls.manager = make_user("ab-remind-manager@example.com", ["Sales Manager"]).name
		cls.clerk = make_user("ab-remind-clerk@example.com", ["Sales User"]).name

	def setUp(self):
		frappe.db.delete("Notification Log")
		frappe.db.delete("ToDo")
		frappe.db.delete("Document Reminder Rule", {"rule_name": ["like", "AB %"]})
		set_settings(also_email=0)

	def test_before_covers_from_n_days_ahead_until_the_date(self):
		due_today, due_soon = make_todo(0), make_todo(2)
		far, late = make_todo(5), make_todo(-1)

		names = {d.name for d in matching_documents(make_rule(when="Before", days=2))}

		self.assertEqual(names, {due_today.name, due_soon.name})
		self.assertTrue({far.name, late.name}.isdisjoint(names))

	def test_on_and_after(self):
		today_todo, late, very_late = make_todo(0), make_todo(-1), make_todo(-5)

		on = {d.name for d in matching_documents(make_rule("AB on", when="On"))}
		after = {d.name for d in matching_documents(make_rule("AB after", when="After", days=2))}

		self.assertEqual(on, {today_todo.name})
		self.assertEqual(after, {very_late.name})
		self.assertNotIn(late.name, after)

	def test_filters_leave_out_finished_documents(self):
		open_todo, closed = make_todo(1), make_todo(1, status="Closed")
		names = {d.name for d in matching_documents(make_rule())}

		self.assertEqual(names, {open_todo.name})
		self.assertNotIn(closed.name, names)

	def test_one_digest_per_person_with_the_count(self):
		make_todo(0), make_todo(1)

		told = run_rule(make_rule())

		self.assertEqual(told[self.manager], 2)
		self.assertEqual(bells(self.manager), ["2 ToDo due within 2 days"])
		log = frappe.get_all("Notification Log", filters={"for_user": self.manager}, fields=["link", "email_content", "type"])[0]
		self.assertEqual(log.type, "Alert")
		self.assertTrue(log.link.startswith("/app/todo?name="))
		self.assertEqual(len(log.email_content.split(", ")), 2)
		self.assertEqual(bells(self.clerk), [])

	def test_document_owner_can_be_told_too(self):
		mine = make_todo(1, owner=self.clerk)
		make_todo(1, owner="Administrator")

		told = run_rule(make_rule(notify_owner=1, roles=[]))

		self.assertEqual(told[self.clerk], 1)
		self.assertIn(mine.name, frappe.get_all("Notification Log", filters={"for_user": self.clerk}, pluck="email_content")[0])

	def test_the_same_message_is_not_repeated_the_same_day(self):
		make_todo(0)
		rule = make_rule()

		run_rule(rule)
		run_rule(rule)

		self.assertEqual(len(bells(self.manager)), 1)

	def test_nothing_matching_sends_nothing(self):
		make_todo(30)
		self.assertEqual(run_rule(make_rule()), {})
		self.assertEqual(bells(self.manager), [])

	def test_disabled_rules_are_skipped_and_a_broken_rule_does_not_stop_the_others(self):
		make_todo(0)
		make_rule("AB disabled", enabled=0)
		broken = make_rule("AB broken")
		frappe.db.set_value("Document Reminder Rule", broken.name, "filters", "not json")
		make_rule("AB works")

		sent = run_document_reminders()

		self.assertNotIn("AB disabled", sent)
		self.assertEqual(sent["AB works"][self.manager], 1)
		self.assertNotIn("AB broken", sent)

	def test_message_placeholders(self):
		rule = make_rule(subject="{count} {doctype} in {days} days {other}")
		self.assertEqual(fill_subject(rule, 4), "4 ToDo in 2 days {other}")

	def test_a_rule_must_make_sense(self):
		bad = [
			{"date_field": "nothing_here"},
			{"date_field": "description"},
			{"days": -1},
			{"filters": "not json"},
			{"filters": '{"a": 1}'},
			{"roles": [], "notify_owner": 0},
		]
		for change in bad:
			with self.assertRaises(frappe.ValidationError, msg=str(change)):
				make_rule("AB bad", **change)

	def test_email_goes_out_only_when_asked_and_when_there_is_a_mailbox(self):
		make_todo(0)
		rule = make_rule()

		with patch.object(notify, "_send_email") as send:
			run_rule(rule)
			send.assert_not_called()

		frappe.db.delete("Notification Log")
		set_settings(also_email=1)
		with patch.object(notify, "_send_email") as send:
			run_rule(rule)
			self.assertIn(self.manager, [u for call in send.call_args_list for u in call.args[0]])

		with patch.object(notify, "has_outgoing_account", return_value=False), patch("frappe.sendmail") as sendmail:
			notify._send_email([self.manager], "Subject", "Body")
			sendmail.assert_not_called()

		with patch.object(notify, "has_outgoing_account", return_value=True), patch("frappe.sendmail") as sendmail:
			notify._send_email([self.manager], "Subject", "Body")
			sendmail.assert_called_once()
			self.assertTrue(sendmail.call_args.kwargs["delayed"])


class TestDefaultReminderRules(AlBuraqTestCase):
	EXPECTED = {
		"Purchase Orders due for delivery",
		"Purchase Invoices due for payment",
		"Sales Invoices overdue",
		"Delivery Notes not yet submitted",
		"Quotations about to expire",
		"Batches about to expire",
	}

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_company()

	def test_the_shipped_rules_are_valid_and_seeded_once(self):
		frappe.db.delete("Document Reminder Rule", {"rule_name": ["in", list(self.EXPECTED)]})

		seed_batch3_defaults.execute()
		seed_batch3_defaults.execute()

		names = frappe.get_all("Document Reminder Rule", filters={"rule_name": ["in", list(self.EXPECTED)]}, pluck="name")
		self.assertEqual(set(names), self.EXPECTED)
		for name in names:
			rule = frappe.get_doc("Document Reminder Rule", name)
			self.assertEqual(bool(rule.enabled), name != "Sales Invoices overdue")  # that one ships switched off
			self.assertTrue(rule.roles or rule.notify_owner)
			matching_documents(rule)  # the filters and date field really work on a live query

	def test_expiry_tiers_are_seeded_without_overwriting_edits(self):
		settings = frappe.get_doc("Al Buraq Settings")
		settings.set("expiry_offer_tiers", [{"days_to_expiry": 10, "discount_percent": 50}])
		settings.save(ignore_permissions=True)

		seed_batch3_defaults.execute()

		tiers = frappe.get_doc("Al Buraq Settings").expiry_offer_tiers
		self.assertEqual([(t.days_to_expiry, t.discount_percent) for t in tiers], [(10, 50)])
