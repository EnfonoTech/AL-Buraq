import frappe
from frappe.utils import flt

from al_buraq.tests.utils import AlBuraqTestCase, ensure_company, make_item, make_quotation, make_user
from al_buraq.utils.quotation_profit import set_quotation_profit


class TestQuotationProfit(AlBuraqTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_company()

	def test_profit_uses_valuation_rate(self):
		make_item("AB-PROFIT-1", valuation_rate=60)
		q = make_quotation([{"item_code": "AB-PROFIT-1", "qty": 2, "rate": 100, "valuation_rate": 60}])

		self.assertEqual(flt(q.base_net_total), 200)
		self.assertEqual(flt(q.custom_total_profit), 80)
		self.assertEqual(flt(q.custom_profit_percent), 40)
		self.assertFalse(q.custom_profit_note)

	def test_last_purchase_rate_is_the_fallback_cost(self):
		make_item("AB-PROFIT-2", last_purchase_rate=70)
		q = make_quotation([{"item_code": "AB-PROFIT-2", "qty": 1, "rate": 100}])

		self.assertEqual(flt(q.custom_total_profit), 30)
		self.assertEqual(flt(q.custom_profit_percent), 30)

	def test_stock_item_without_any_cost_is_flagged(self):
		make_item("AB-PROFIT-3")
		q = make_quotation([{"item_code": "AB-PROFIT-3", "qty": 1, "rate": 100}])

		self.assertEqual(flt(q.custom_total_profit), 100)
		self.assertIn("1", q.custom_profit_note)

	def test_service_item_without_cost_is_not_flagged(self):
		make_item("AB-PROFIT-4", is_stock_item=0)
		q = make_quotation([{"item_code": "AB-PROFIT-4", "qty": 1, "rate": 100}])

		self.assertEqual(flt(q.custom_total_profit), 100)
		self.assertFalse(q.custom_profit_note)

	def test_profit_follows_the_net_total_after_discount(self):
		make_item("AB-PROFIT-5", valuation_rate=50)
		q = make_quotation(
			[{"item_code": "AB-PROFIT-5", "qty": 1, "price_list_rate": 100, "discount_percentage": 10, "valuation_rate": 50}]
		)

		self.assertEqual(flt(q.base_net_total), 90)
		self.assertEqual(flt(q.custom_total_profit), 40)
		self.assertEqual(flt(q.custom_profit_percent), 44.44)

	def test_alternative_items_are_left_out(self):
		doc = frappe._dict(
			base_net_total=100,
			items=[
				frappe._dict(item_code=None, idx=1, stock_qty=1, qty=1, conversion_factor=1, valuation_rate=40),
				frappe._dict(
					item_code=None, idx=2, stock_qty=1, qty=1, conversion_factor=1, valuation_rate=999, is_alternative=1
				),
			],
		)
		doc.get = lambda key, default=None: doc[key] if key in doc else default
		doc.precision = lambda fieldname: 2

		set_quotation_profit(doc)

		self.assertEqual(doc.custom_total_profit, 60)

	def test_zero_revenue_does_not_divide_by_zero(self):
		doc = frappe._dict(base_net_total=0, items=[])
		doc.get = lambda key, default=None: doc[key] if key in doc else default
		doc.precision = lambda fieldname: 2

		set_quotation_profit(doc)

		self.assertEqual(doc.custom_profit_percent, 0)

	def test_profit_block_is_only_readable_by_manager_roles(self):
		make_item("AB-PROFIT-6", valuation_rate=10)
		q = make_quotation([{"item_code": "AB-PROFIT-6", "qty": 1, "rate": 20, "valuation_rate": 10}])
		make_user("ab-sales-user@example.com", ["Sales User"])
		make_user("ab-sales-manager@example.com", ["Sales Manager"])

		try:
			frappe.set_user("ab-sales-user@example.com")
			self.assertNotIn(2, frappe.get_doc("Quotation", q.name).get_permlevel_access("read"))

			frappe.set_user("ab-sales-manager@example.com")
			self.assertIn(2, frappe.get_doc("Quotation", q.name).get_permlevel_access("read"))
		finally:
			frappe.set_user("Administrator")
