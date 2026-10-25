import frappe
from frappe.utils import flt

from al_buraq.tests.utils import AlBuraqTestCase, ensure_company, make_customer, make_item, make_quotation, make_user
from al_buraq.utils.price_discount import best_rule, check_max_discount


def make_rule(**kwargs):
	values = {"doctype": "Price and Discount Rule", "enabled": 1, "default_discount_percent": 5, "max_discount_percent": 10}
	values.update(kwargs)
	rule = frappe.get_doc(values)
	rule.insert(ignore_permissions=True)
	return rule


def rule_row(name, **kwargs):
	row = {"name": name, "priority": 0, "company": None, "item_group": None, "customer_group": None, "min_qty": 0, "max_qty": 0, "default_discount_percent": 0, "max_discount_percent": 0}
	row.update(kwargs)
	return frappe._dict(row)


class TestRuleChoice(AlBuraqTestCase):
	def test_the_most_specific_rule_wins_then_priority(self):
		doc, row = frappe._dict(company="C"), frappe._dict(item_code=None, item_group="Hardware", qty=5)
		general = rule_row("general")
		item_group = rule_row("item-group", item_group="Hardware")
		both = rule_row("both", item_group="Hardware", customer_group="Retail")
		other_group = rule_row("other", item_group="Software")

		self.assertEqual(best_rule([general, other_group], doc, row, "Retail").name, "general")
		self.assertEqual(best_rule([general, item_group, other_group], doc, row, "Retail").name, "item-group")
		self.assertEqual(best_rule([general, item_group, both], doc, row, "Retail").name, "both")
		self.assertEqual(best_rule([general, item_group, both], doc, row, "Wholesale").name, "item-group")

		low, high = rule_row("low", item_group="Hardware", priority=1), rule_row("high", item_group="Hardware", priority=5)
		self.assertEqual(best_rule([low, high], doc, row, None).name, "high")

	def test_quantity_band_and_company(self):
		doc = frappe._dict(company="C")
		bulk = rule_row("bulk", min_qty=10, max_qty=50)
		mine = rule_row("mine", company="C")
		theirs = rule_row("theirs", company="D")

		self.assertIsNone(best_rule([bulk], doc, frappe._dict(item_code=None, item_group=None, qty=9), None))
		self.assertEqual(best_rule([bulk], doc, frappe._dict(item_code=None, item_group=None, qty=10), None).name, "bulk")
		self.assertIsNone(best_rule([bulk], doc, frappe._dict(item_code=None, item_group=None, qty=51), None))
		self.assertEqual(best_rule([theirs, mine], doc, frappe._dict(item_code=None, item_group=None, qty=1), None).name, "mine")


class TestRuleValidation(AlBuraqTestCase):
	def test_bad_rules_are_refused(self):
		bad = [
			{"min_qty": -1},
			{"min_qty": 10, "max_qty": 5},
			{"default_discount_percent": 101},
			{"default_discount_percent": 15, "max_discount_percent": 10},
		]
		for change in bad:
			with self.assertRaises(frappe.ValidationError, msg=str(change)):
				make_rule(**change)

	def test_no_maximum_means_any_default_is_fine(self):
		self.assertTrue(make_rule(default_discount_percent=30, max_discount_percent=0).name.startswith("PDR-"))


class TestDiscountOnQuotation(AlBuraqTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_company()
		cls.customer = make_customer("AB Retail Customer")
		frappe.db.set_value("Customer", cls.customer, "customer_group", "Individual")
		cls.item = make_item("AB-PD-1").name
		cls.rep = make_user("ab-pd-rep@example.com", ["Sales User"]).name
		cls.manager = make_user("ab-pd-manager@example.com", ["Sales Manager", "Sales User"]).name

	def setUp(self):
		frappe.db.delete("Price and Discount Rule")

	def tearDown(self):
		frappe.set_user("Administrator")

	def _quote(self, discount=0, **row):
		return make_quotation(
			[{"item_code": self.item, "qty": 2, "price_list_rate": 100, "discount_percentage": discount, **row}]
		)

	def test_a_new_row_gets_the_default_discount_and_the_rate_follows(self):
		rule = make_rule(customer_group="Individual", default_discount_percent=5, max_discount_percent=10)

		row = self._quote().items[0]

		self.assertEqual(flt(row.discount_percentage), 5)
		self.assertEqual(flt(row.rate), 95)
		self.assertEqual(row.custom_rule_applied, rule.name)

	def test_a_discount_set_by_hand_is_left_alone(self):
		make_rule(customer_group="Individual")
		row = self._quote(discount=3).items[0]

		self.assertEqual(flt(row.discount_percentage), 3)
		self.assertFalse(row.custom_rule_applied)

	def test_setting_it_back_to_zero_sticks(self):
		make_rule(customer_group="Individual")
		quote = self._quote()
		quote.items[0].discount_percentage = 0
		quote.items[0].rate = 100  # what the form does when the discount is cleared
		quote.save()

		self.assertEqual(flt(quote.items[0].discount_percentage), 0)
		self.assertEqual(flt(quote.items[0].rate), 100)

	def test_rules_that_do_not_match_or_are_disabled_do_nothing(self):
		make_rule(customer_group="Government")
		make_rule(customer_group="Individual", enabled=0)
		make_rule(customer_group="Individual", min_qty=100)

		self.assertEqual(flt(self._quote().items[0].discount_percentage), 0)

	def test_over_the_maximum_is_refused_for_a_salesperson_but_not_a_manager(self):
		make_rule(customer_group="Individual", default_discount_percent=5, max_discount_percent=10)

		frappe.set_user(self.rep)
		with self.assertRaises(frappe.ValidationError) as caught:
			self._quote(discount=15)
		self.assertIn("10.0% allowed", str(caught.exception))
		self._quote(discount=10)  # at the maximum is fine

		frappe.set_user(self.manager)
		self.assertEqual(flt(self._quote(discount=15).items[0].discount_percentage), 15)

	def test_a_quote_for_a_lead_is_not_matched_by_a_customer_group_rule(self):
		make_rule(customer_group="Individual")
		rule_doc = frappe._dict(doctype="Quotation", quotation_to="Lead", party_name="LEAD-1", company=None)
		from al_buraq.utils.price_discount import customer_group_of

		self.assertIsNone(customer_group_of(rule_doc))
