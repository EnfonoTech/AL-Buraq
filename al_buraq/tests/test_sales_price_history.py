import frappe
from erpnext.controllers.sales_and_purchase_return import make_return_doc
from frappe.utils import add_days, nowdate

from al_buraq.al_buraq.report.sales_price_history.sales_price_history import execute
from al_buraq.tests.utils import (
	COMPANY,
	AlBuraqTestCase,
	ensure_company,
	ensure_sales_person_field,
	make_customer,
	make_item,
	make_sales_invoice,
	make_sales_person,
)


class TestSalesPriceHistory(AlBuraqTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_company()
		ensure_sales_person_field()
		cls.rep_a = make_sales_person("AB Rep A")
		cls.rep_b = make_sales_person("AB Rep B")
		cls.item = "AB-SPH-" + frappe.generate_hash(length=6).upper()
		make_item(cls.item, is_stock_item=0, approved=True)
		cls.today = nowdate()
		cls.invoices = [
			make_sales_invoice(cls.item, 2, 100, add_days(cls.today, -10), sales_person=cls.rep_a),
			make_sales_invoice(cls.item, 3, 120, add_days(cls.today, -5), sales_person=cls.rep_a),
			make_sales_invoice(cls.item, 1, 90, add_days(cls.today, -1), sales_person=cls.rep_b),
			make_sales_invoice(cls.item, 4, 110, add_days(cls.today, -2), team_member=cls.rep_b),
		]

	def _run(self, **filters):
		base = {"company": COMPANY, "item_code": self.item}
		return execute({**base, **filters})

	def test_detail_has_one_row_per_line_newest_first(self):
		columns, rows = self._run()

		self.assertEqual(len(rows), 4)
		self.assertEqual([r["posting_date"] for r in rows], sorted((r["posting_date"] for r in rows), reverse=True))
		self.assertIn("delivery_note", [c["fieldname"] for c in columns])

	def test_sales_person_comes_from_the_field_then_the_sales_team(self):
		_, rows = self._run()
		by_invoice = {r["sales_invoice"]: r["sales_person"] for r in rows}

		self.assertEqual(by_invoice[self.invoices[0].name], self.rep_a)
		self.assertEqual(by_invoice[self.invoices[2].name], self.rep_b)
		self.assertEqual(by_invoice[self.invoices[3].name], self.rep_b)  # from the Sales Team table

	def test_filter_by_sales_person(self):
		_, rows = self._run(sales_person=self.rep_b)

		self.assertEqual({r["sales_invoice"] for r in rows}, {self.invoices[2].name, self.invoices[3].name})
		self.assertEqual({r["sales_person"] for r in rows}, {self.rep_b})

	def test_date_window(self):
		_, rows = self._run(from_date=add_days(self.today, -6), to_date=add_days(self.today, -2))

		self.assertEqual(
			{r["sales_invoice"] for r in rows}, {self.invoices[1].name, self.invoices[3].name}
		)

	def test_customer_filter_and_returns_are_left_out(self):
		other = make_customer("AB Other " + frappe.generate_hash(length=5))
		item = make_item("AB-SPH-RET-" + frappe.generate_hash(length=4), is_stock_item=0, approved=True).name
		inv = make_sales_invoice(item, 1, 500, self.today, sales_person=self.rep_a, customer=other)

		_, rows = self._run(customer=other, item_code=item)
		self.assertEqual([r["sales_invoice"] for r in rows], [inv.name])

		credit_note = make_return_doc("Sales Invoice", inv.name)
		credit_note.insert(ignore_permissions=True)
		credit_note.submit()
		_, rows = self._run(customer=other, item_code=item)
		self.assertEqual([r["sales_invoice"] for r in rows], [inv.name])

	def test_rate_per_stock_uom_follows_the_conversion_factor(self):
		item = make_item("AB-SPH-BOX-" + frappe.generate_hash(length=4), is_stock_item=0, approved=True)
		item.append("uoms", {"uom": "Box", "conversion_factor": 10})
		item.save(ignore_permissions=True)
		inv = frappe.new_doc("Sales Invoice")
		inv.update({"company": COMPANY, "customer": make_customer(), "posting_date": self.today, "set_posting_time": 1})
		inv.append("items", {"item_code": item.name, "qty": 2, "uom": "Box", "rate": 500})
		inv.insert(ignore_permissions=True)
		inv.submit()

		_, rows = execute({"company": COMPANY, "item_code": item.name})

		self.assertEqual(rows[0]["rate"], 500)
		self.assertEqual(rows[0]["rate_per_stock_uom"], 50)

	def test_summary_per_item_and_sales_person(self):
		columns, rows = self._run(group_by="Item and Sales Person")
		by_person = {r["sales_person"]: r for r in rows}

		self.assertIn("avg_rate", [c["fieldname"] for c in columns])
		a = by_person[self.rep_a]
		self.assertEqual((a["invoices"], a["qty"]), (2, 5))
		self.assertEqual((a["min_rate"], a["max_rate"]), (100, 120))
		self.assertEqual(a["avg_rate"], (2 * 100 + 3 * 120) / 5)  # weighted by quantity
		self.assertEqual(a["last_rate"], 120)
		self.assertEqual(str(a["last_date"]), add_days(self.today, -5))

		b = by_person[self.rep_b]
		self.assertEqual((b["invoices"], b["qty"]), (2, 5))
		self.assertEqual((b["min_rate"], b["max_rate"], b["last_rate"]), (90, 110, 90))

	def test_company_is_required(self):
		with self.assertRaises(frappe.ValidationError):
			execute({})
