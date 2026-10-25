import frappe

from al_buraq.tests.utils import AlBuraqTestCase, ensure_company, make_item


def make_price(item_code, rate, selling=1, uom=None, price_list="Standard Selling"):
	doc = frappe.get_doc(
		{
			"doctype": "Item Price",
			"item_code": item_code,
			"price_list": price_list,
			"price_list_rate": rate,
			"selling": selling,
			"buying": 0 if selling else 1,
			"uom": uom,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestMaxSellingRate(AlBuraqTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_company()

	def test_standard_rate_may_not_exceed_maximum(self):
		with self.assertRaises(frappe.ValidationError):
			make_item("AB-MAX-1", standard_rate=120, custom_max_selling_rate=100)

		item = make_item("AB-MAX-1", standard_rate=100, custom_max_selling_rate=100)
		self.assertEqual(item.custom_max_selling_rate, 100)

	def test_negative_maximum_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_item("AB-MAX-2", custom_max_selling_rate=-5)

	def test_no_maximum_means_no_limit(self):
		make_item("AB-MAX-3")
		self.assertTrue(make_price("AB-MAX-3", 99999).name)

	def test_selling_price_above_maximum_is_refused(self):
		make_item("AB-MAX-4", custom_max_selling_rate=100)

		with self.assertRaises(frappe.ValidationError):
			make_price("AB-MAX-4", 100.01)

		self.assertTrue(make_price("AB-MAX-4", 100).name)

	def test_buying_price_is_not_limited(self):
		make_item("AB-MAX-5", custom_max_selling_rate=100)
		self.assertTrue(make_price("AB-MAX-5", 500, selling=0, price_list="Standard Buying").name)

	def test_price_in_another_uom_is_converted(self):
		item = make_item("AB-MAX-6", custom_max_selling_rate=10)
		item.append("uoms", {"uom": "Box", "conversion_factor": 10})
		item.save(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			make_price("AB-MAX-6", 101, uom="Box")

		self.assertTrue(make_price("AB-MAX-6", 100, uom="Box").name)
