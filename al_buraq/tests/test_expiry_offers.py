import frappe
from frappe.utils import add_days, flt, getdate, nowdate

from al_buraq.al_buraq.report.expiring_stock_and_suggested_offers.expiring_stock_and_suggested_offers import execute
from al_buraq.api.expiry_offer import create_expiry_offer
from al_buraq.patches import seed_batch3_defaults
from al_buraq.tasks.document_reminders import matching_documents, run_rule
from al_buraq.tests.test_job_tracking import set_settings
from al_buraq.tests.utils import AlBuraqTestCase, bells, ensure_company, make_item, make_user
from al_buraq.utils.expiry_offers import expiring_batches, get_tiers, suggest_discount


def set_tiers(*tiers):
	settings = frappe.get_doc("Al Buraq Settings")
	settings.set("expiry_offer_tiers", [{"days_to_expiry": d, "discount_percent": p} for d, p in tiers])
	settings.save(ignore_permissions=True)
	frappe.clear_document_cache("Al Buraq Settings", "Al Buraq Settings")


def make_batch(item, name, days_to_expiry, qty=10, disabled=0):
	batch = frappe.get_doc(
		{"doctype": "Batch", "batch_id": name, "item": item, "expiry_date": add_days(nowdate(), days_to_expiry)}
	)
	batch.insert(ignore_permissions=True)
	frappe.db.set_value("Batch", batch.name, {"batch_qty": qty, "disabled": disabled}, update_modified=False)
	return batch.name


class TestSuggestedDiscount(AlBuraqTestCase):
	def test_first_band_that_fits(self):
		tiers = [(30, 20), (60, 10)]
		self.assertEqual(suggest_discount(0, tiers), 20)
		self.assertEqual(suggest_discount(30, tiers), 20)
		self.assertEqual(suggest_discount(31, tiers), 10)
		self.assertEqual(suggest_discount(60, tiers), 10)
		self.assertIsNone(suggest_discount(61, tiers))

	def test_expired_stock_gets_no_offer(self):
		self.assertIsNone(suggest_discount(-1, [(30, 20)]))

	def test_tiers_come_sorted_from_the_settings(self):
		set_tiers((60, 10), (30, 20))
		self.assertEqual(get_tiers(), [(30, 20.0), (60, 10.0)])


class TestExpiringStock(AlBuraqTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_company()
		set_tiers((30, 20), (60, 10))
		cls.item = make_item("AB-EXP-1", has_batch_no=1, has_expiry_date=1, standard_rate=200).name
		cls.other = make_item("AB-EXP-2", has_batch_no=1, has_expiry_date=1, item_group="Products", standard_rate=50).name
		cls.soon = make_batch(cls.item, "AB-B-SOON", 10)
		cls.later = make_batch(cls.item, "AB-B-LATER", 45)
		cls.far = make_batch(cls.item, "AB-B-FAR", 200)
		cls.gone = make_batch(cls.item, "AB-B-GONE", -3)
		cls.empty = make_batch(cls.item, "AB-B-EMPTY", 5, qty=0)
		cls.off = make_batch(cls.item, "AB-B-OFF", 5, disabled=1)
		cls.other_group = make_batch(cls.other, "AB-B-OTHER", 20)

	def _rows(self, **kwargs):
		return {r["batch"]: r for r in expiring_batches(**kwargs)}

	def test_lists_stock_expiring_inside_the_widest_band_soonest_first(self):
		rows = expiring_batches()
		names = [r["batch"] for r in rows if r["item_code"] in (self.item, self.other)]

		self.assertEqual(names, [self.gone, self.soon, self.other_group, self.later])
		self.assertNotIn(self.far, names)
		self.assertNotIn(self.empty, names)  # no stock
		self.assertNotIn(self.off, names)  # disabled

	def test_suggestion_and_offer_rate(self):
		rows = self._rows()
		self.assertEqual(rows[self.soon]["suggested_discount"], 20)
		self.assertEqual(rows[self.soon]["offer_rate"], 160)
		self.assertEqual(rows[self.later]["suggested_discount"], 10)
		self.assertEqual(rows[self.later]["offer_rate"], 180)
		self.assertEqual(rows[self.soon]["days_left"], 10)

	def test_expired_stock_is_shown_without_an_offer(self):
		row = self._rows()[self.gone]
		self.assertEqual(row["days_left"], -3)
		self.assertIsNone(row["suggested_discount"])
		self.assertIsNone(row["offer_rate"])

	def test_item_price_beats_the_standard_rate(self):
		self.assertEqual(self._rows()[self.other_group]["selling_rate"], 50)  # the item's own rate, via its first price
		frappe.db.set_value("Item Price", {"item_code": self.other, "selling": 1}, "price_list_rate", 80)
		self.assertEqual(self._rows()[self.other_group]["selling_rate"], 80)

	def test_filters(self):
		self.assertEqual(set(self._rows(item_group="Products")), {self.other_group})
		self.assertEqual(set(r for r in self._rows(within_days=15) if r in (self.soon, self.later)), {self.soon})

	def test_the_report_returns_the_same_rows(self):
		columns, rows = execute({"item_group": "Products"})
		self.assertEqual([r["batch"] for r in rows], [self.other_group])
		self.assertIn("suggested_discount", [c["fieldname"] for c in columns])

	def test_reminder_rule_tells_stock_managers(self):
		manager = make_user("ab-exp-stock@example.com", ["Stock Manager"]).name
		frappe.db.delete("Document Reminder Rule", {"rule_name": "Batches about to expire"})
		seed_batch3_defaults.execute()
		frappe.db.delete("Notification Log")

		rule = frappe.get_doc("Document Reminder Rule", "Batches about to expire")
		due = {d.name for d in matching_documents(rule)}
		told = run_rule(rule)

		self.assertTrue({self.soon, self.other_group} <= due)  # the 10 and 20 day batches
		self.assertTrue({self.later, self.far, self.gone, self.empty, self.off}.isdisjoint(due))
		self.assertEqual(told[manager], len(due))
		self.assertIn("batches expire within 30 days", bells(manager)[0])


class TestCreateExpiryOffer(AlBuraqTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_company()
		cls.item = make_item("AB-OFFER-1").name
		cls.clerk = make_user("ab-offer-clerk@example.com", ["Desk User"]).name

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_creates_a_switched_off_rule_until_the_batch_expires(self):
		valid_upto = add_days(nowdate(), 20)

		name = create_expiry_offer(self.item, 15, valid_upto)

		rule = frappe.get_doc("Pricing Rule", name)
		self.assertEqual(rule.disable, 1)
		self.assertEqual(flt(rule.discount_percentage), 15)
		self.assertEqual(rule.rate_or_discount, "Discount Percentage")
		self.assertEqual(getdate(rule.valid_upto), getdate(valid_upto))
		self.assertEqual([i.item_code for i in rule.items], [self.item])
		self.assertEqual(rule.selling, 1)

	def test_bad_requests_are_refused(self):
		for args in ((self.item, 0, nowdate()), (self.item, 101, nowdate()), ("NO-SUCH-ITEM", 10, nowdate())):
			with self.assertRaises(frappe.ValidationError, msg=str(args)):
				create_expiry_offer(*args)

	def test_needs_the_right_to_create_pricing_rules(self):
		frappe.set_user(self.clerk)
		with self.assertRaises(frappe.PermissionError):
			create_expiry_offer(self.item, 10, nowdate())
