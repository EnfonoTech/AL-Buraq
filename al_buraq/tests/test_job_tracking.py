import frappe
from frappe.utils import add_days, nowdate

from al_buraq.al_buraq.report.job_tracker.job_tracker import execute as job_tracker
from al_buraq.api.job import make_job_from_opportunity
from al_buraq.patches import grant_job_record_roles
from al_buraq.tasks.enquiry_reminders import send_unconverted_enquiry_reminders, unconverted_enquiries
from al_buraq.tests.utils import (
	AlBuraqTestCase,
	bells,
	ensure_company,
	make_customer,
	make_employee,
	make_opportunity,
	make_user,
)

DEPARTMENTS = ("Sales", "Purchase", "Operations")


def department(name):
	return frappe.db.get_value("Department", {"department_name": name, "company": ["is", "set"]}, "name") or frappe.db.get_value(
		"Department", {"department_name": name}, "name"
	)


def make_job(stages=(), status=None, **kwargs):
	job = frappe.new_doc("Job Record")
	job.update({"job_name": "AB Test Job", "customer": make_customer(), "date": nowdate(), **kwargs})
	for dept, state in stages:
		job.append("stages", {"department": department(dept), "status": state})
	if status:
		job.status = status
	job.insert(ignore_permissions=True)
	return job


def set_settings(**values):
	settings = frappe.get_doc("Al Buraq Settings")
	for key, value in values.items():
		if key == "default_stages":
			settings.set("default_stages", [{"department": department(d)} for d in value])
		else:
			settings.set(key, value)
	settings.save(ignore_permissions=True)
	frappe.clear_document_cache("Al Buraq Settings", "Al Buraq Settings")


class TestJobRecord(AlBuraqTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_company()

	def test_progress_and_status_follow_the_stages(self):
		job = make_job([("Sales", "Pending"), ("Purchase", "Pending")])
		self.assertEqual((job.status, job.progress), ("Open", 0))

		job.stages[0].status = "Done"
		job.save()
		self.assertEqual((job.status, job.progress), ("In Progress", 50))
		self.assertTrue(job.stages[0].end_date)

		job.stages[1].status = "Done"
		job.save()
		self.assertEqual((job.status, job.progress), ("Completed", 100))

		job.stages[1].status = "Blocked"
		job.save()
		self.assertEqual(job.status, "In Progress")

	def test_on_hold_is_kept_by_hand(self):
		job = make_job([("Sales", "Done")], status="On Hold")
		self.assertEqual(job.status, "On Hold")

	def test_stage_problems_are_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_job([("Sales", "Pending"), ("Sales", "Pending")])

		job = make_job([("Sales", "Pending")])
		job.stages[0].start_date = nowdate()
		job.stages[0].end_date = add_days(nowdate(), -1)
		with self.assertRaises(frappe.ValidationError):
			job.save()

	def test_stages_can_be_updated_after_submit(self):
		job = make_job([("Sales", "Pending"), ("Operations", "Pending")])
		job.submit()

		job.reload()
		job.stages[0].status = "Done"
		job.save()  # update after submit

		job.reload()
		self.assertEqual((job.docstatus, job.status, job.progress), (1, "In Progress", 50))

	def test_each_job_gets_its_own_number(self):
		first, second = make_job(), make_job()
		self.assertNotEqual(first.name, second.name)
		self.assertRegex(first.name, r"^JOB-\d{4}-\d{5}$")


class TestCreateJob(AlBuraqTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_company()
		make_user("ab-job-nobody@example.com", ["Desk User"])
		make_user("ab-job-sales@example.com", ["Sales User"])

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_job_is_made_from_the_enquiry_with_the_default_stages(self):
		set_settings(default_stages=["Sales", "Operations"])
		opp = make_opportunity()

		result = make_job_from_opportunity(opp.name)

		job = frappe.get_doc("Job Record", result["name"])
		self.assertEqual(result["created"], 1)
		self.assertEqual(job.opportunity, opp.name)
		self.assertEqual(job.customer, opp.party_name)
		self.assertEqual([s.department for s in job.stages], [department("Sales"), department("Operations")])
		self.assertEqual(job.status, "Open")

	def test_asking_twice_returns_the_same_job(self):
		opp = make_opportunity()
		first = make_job_from_opportunity(opp.name)
		again = make_job_from_opportunity(opp.name)

		self.assertEqual(again, {"name": first["name"], "created": 0})
		self.assertEqual(frappe.db.count("Job Record", {"opportunity": opp.name}), 1)

	def test_sales_user_can_create_a_job(self):
		opp = make_opportunity()
		frappe.set_user("ab-job-sales@example.com")
		self.assertTrue(make_job_from_opportunity(opp.name)["created"])

	def test_user_without_job_rights_is_refused(self):
		opp = make_opportunity()
		frappe.set_user("ab-job-nobody@example.com")
		with self.assertRaises(frappe.PermissionError):
			make_job_from_opportunity(opp.name)


class TestJobTracker(AlBuraqTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_company()
		cls.customer = make_customer("AB Tracker Customer")
		cls.active = make_job([("Sales", "Done"), ("Purchase", "In Progress"), ("Operations", "Pending")], job_name="Tracker active", customer=cls.customer)
		cls.blocked = make_job([("Sales", "Done"), ("Operations", "Blocked")], job_name="Tracker blocked", customer=cls.customer)
		cls.finished = make_job([("Sales", "Done")], job_name="Tracker finished", customer=cls.customer)

	def _run(self, **filters):
		return job_tracker({"customer": self.customer, **filters})

	def test_one_row_per_job_with_a_column_per_department(self):
		columns, rows = self._run()
		labels = [c["label"] for c in columns]

		self.assertEqual({r["job_name"] for r in rows}, {"Tracker active", "Tracker blocked"})  # completed is hidden
		for dept in ("Sales", "Purchase", "Operations"):
			self.assertIn(department(dept), labels)

		active = next(r for r in rows if r["job_name"] == "Tracker active")
		by_label = {c["label"]: c["fieldname"] for c in columns}
		self.assertEqual(active[by_label[department("Purchase")]], "In Progress")
		self.assertEqual(active["current_stage"], department("Purchase"))
		self.assertEqual(round(active["progress"]), 33)

	def test_a_blocked_stage_is_called_out(self):
		_, rows = self._run()
		blocked = next(r for r in rows if r["job_name"] == "Tracker blocked")
		self.assertEqual(blocked["current_stage"], department("Operations") + " (blocked)")

	def test_filters(self):
		_, rows = self._run(show_completed=1)
		self.assertEqual(len(rows), 3)

		_, rows = self._run(status="Completed")
		self.assertEqual([r["job_name"] for r in rows], ["Tracker finished"])

		_, rows = self._run(department=department("Purchase"))
		self.assertEqual([r["job_name"] for r in rows], ["Tracker active"])

		_, rows = self._run(from_date=add_days(nowdate(), 1))
		self.assertEqual(rows, [])

	def test_days_open_is_blank_for_a_finished_job(self):
		_, rows = self._run(show_completed=1)
		self.assertIsNone(next(r for r in rows if r["job_name"] == "Tracker finished")["days_open"])
		self.assertEqual(next(r for r in rows if r["job_name"] == "Tracker active")["days_open"], 0)


class TestEnquiryReminders(AlBuraqTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_company()
		cls.rep = make_user("ab-rep@example.com", ["Sales User"]).name
		cls.boss = make_user("ab-boss@example.com", ["Sales Manager"]).name
		cls.supervisor = make_user("ab-supervisor@example.com", ["Sales Supervisor"]).name

	def setUp(self):
		frappe.db.delete("Notification Log")
		frappe.db.delete("Job Record")
		frappe.db.delete("Opportunity")
		set_settings(enquiry_reminder_days=3, enquiry_reminder_role="Sales Supervisor")

	def test_old_enquiries_without_a_job_are_listed_and_the_rest_are_not(self):
		old = make_opportunity(owner=self.rep, days_old=5)
		recent = make_opportunity(owner=self.rep, days_old=1)
		converted = make_opportunity(owner=self.rep, days_old=9)
		make_job_from_opportunity(converted.name)
		lost = make_opportunity(owner=self.rep, days_old=9, status="Lost")

		names = {o.name for o in unconverted_enquiries(3)}

		self.assertIn(old.name, names)
		self.assertTrue({recent.name, converted.name, lost.name}.isdisjoint(names))

	def test_owner_and_the_superior_from_reports_to_are_told(self):
		boss_employee = make_employee(self.boss, first_name="AB Boss")
		make_employee(self.rep, reports_to=boss_employee, first_name="AB Rep")
		opp = make_opportunity(owner=self.rep, days_old=5)

		told = send_unconverted_enquiry_reminders()

		self.assertIn(opp.name, told[self.rep])
		self.assertIn(opp.name, told[self.boss])
		self.assertNotIn(self.supervisor, told)  # the Reports To wins over the fallback role
		self.assertEqual(len(bells(self.rep)), 1)
		self.assertIn("no Job for more than 3 days", bells(self.boss)[0])

	def test_without_a_superior_the_fallback_role_is_told(self):
		frappe.db.set_value("Employee", {"user_id": self.rep}, "reports_to", None)
		make_employee(self.rep, first_name="AB Rep")
		opp = make_opportunity(owner=self.rep, days_old=5)

		told = send_unconverted_enquiry_reminders()

		self.assertIn(opp.name, told[self.supervisor])

	def test_one_message_per_person_per_day(self):
		make_opportunity(owner=self.rep, days_old=5)
		make_opportunity(owner=self.rep, days_old=6)

		send_unconverted_enquiry_reminders()
		send_unconverted_enquiry_reminders()

		self.assertEqual(len(bells(self.rep)), 1)
		self.assertTrue(bells(self.rep)[0].startswith("2 enquiries"))

	def test_zero_days_switches_the_reminder_off(self):
		make_opportunity(owner=self.rep, days_old=30)
		set_settings(enquiry_reminder_days=0)

		self.assertEqual(send_unconverted_enquiry_reminders(), {})
		self.assertEqual(bells(self.rep), [])


class TestJobRecordPermissions(AlBuraqTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.rep = make_user("ab-jobperm-rep@example.com", ["Sales User"]).name

	def test_sites_with_their_own_permission_rows_get_the_shipped_roles(self):
		# the live site: one Custom DocPerm row for System Manager, which hides the shipped file
		frappe.db.delete("Custom DocPerm", {"parent": "Job Record"})
		frappe.get_doc(
			{"doctype": "Custom DocPerm", "parent": "Job Record", "parenttype": "DocType", "parentfield": "permissions", "role": "System Manager", "read": 1, "write": 1, "create": 1}
		).insert(ignore_permissions=True)
		frappe.clear_cache(doctype="Job Record")
		self.assertFalse(frappe.has_permission("Job Record", "create", user=self.rep))

		grant_job_record_roles.execute()
		grant_job_record_roles.execute()  # twice changes nothing

		self.assertTrue(frappe.has_permission("Job Record", "create", user=self.rep))
		self.assertEqual(frappe.db.count("Custom DocPerm", {"parent": "Job Record", "role": "Sales User"}), 1)

	def test_sites_without_them_are_left_alone(self):
		frappe.db.delete("Custom DocPerm", {"parent": "Job Record"})
		grant_job_record_roles.execute()
		self.assertEqual(frappe.db.count("Custom DocPerm", {"parent": "Job Record"}), 0)
