import frappe
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

from al_buraq.api.temporary_item import create_temporary_item, merge_temporary_item
from al_buraq.tests.utils import COMPANY, AlBuraqTestCase, WAREHOUSE, ensure_company, make_item, make_quotation, make_user


class TestTemporaryItem(AlBuraqTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_company()
		make_user("ab-temp-sales@example.com", ["Sales User"])
		make_user("ab-temp-nobody@example.com", ["Desk User"])

	def setUp(self):
		frappe.db.set_default("item_naming_by", "Item Code")

	def tearDown(self):
		frappe.set_user("Administrator")

	def _create(self, name="Chiller Pump 5HP"):
		return create_temporary_item(name, "All Item Groups", "Nos", description="Special order")

	def test_sales_user_can_create_a_temporary_item(self):
		frappe.set_user("ab-temp-sales@example.com")
		self.assertFalse(frappe.has_permission("Item", "create"))

		result = self._create()

		item = frappe.get_doc("Item", result["item_code"])
		self.assertEqual(item.custom_is_temporary, 1)
		self.assertEqual(item.is_stock_item, 1)
		self.assertEqual(item.custom_approval_status, "Pending")
		self.assertEqual(item.item_name, "Chiller Pump 5HP")
		self.assertTrue(item.name.startswith("TMP-"))

	def test_quotation_name_is_recorded_when_given(self):
		make_item("AB-TEMP-BASE")
		q = make_quotation([{"item_code": "AB-TEMP-BASE", "qty": 1, "rate": 10}])

		result = create_temporary_item("Pump", "All Item Groups", "Nos", quotation=q.name)

		self.assertEqual(frappe.db.get_value("Item", result["item_code"], "custom_temp_quotation"), q.name)

	def test_naming_series_is_used_when_the_site_names_items_by_series(self):
		frappe.db.set_default("item_naming_by", "Naming Series")

		result = self._create()

		self.assertFalse(result["item_code"].startswith("TMP-"))
		self.assertEqual(frappe.db.get_value("Item", result["item_code"], "custom_is_temporary"), 1)

	def test_user_who_cannot_edit_quotations_is_refused(self):
		frappe.set_user("ab-temp-nobody@example.com")
		with self.assertRaises(frappe.PermissionError):
			self._create()

	def test_missing_name_or_group_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			create_temporary_item("   ", "All Item Groups", "Nos")
		with self.assertRaises(frappe.ValidationError):
			create_temporary_item("Pump", "No Such Group", "Nos")

	def test_merge_repoints_the_quotation_and_deletes_the_temporary_item(self):
		temp = self._create("Merge Me")["item_code"]
		real = make_item("AB-REAL-1").name
		q = make_quotation([{"item_code": temp, "qty": 3, "rate": 10}])

		merge_temporary_item(temp, real)

		self.assertFalse(frappe.db.exists("Item", temp))
		self.assertEqual(frappe.db.get_value("Quotation Item", {"parent": q.name}, "item_code"), real)

	def test_merge_refuses_unsuitable_pairs(self):
		temp = self._create("Refuse Me")["item_code"]
		other_temp = self._create("Other Temp")["item_code"]
		real = make_item("AB-REAL-2").name

		with self.assertRaises(frappe.ValidationError):
			merge_temporary_item(temp, temp)
		with self.assertRaises(frappe.ValidationError):
			merge_temporary_item(real, temp)  # source is not temporary
		with self.assertRaises(frappe.ValidationError):
			merge_temporary_item(temp, other_temp)  # target is temporary
		self.assertTrue(frappe.db.exists("Item", temp))

	def test_merge_needs_item_rights(self):
		temp = self._create("No Rights")["item_code"]
		real = make_item("AB-REAL-3").name

		frappe.set_user("ab-temp-sales@example.com")
		with self.assertRaises(frappe.PermissionError):
			merge_temporary_item(temp, real)

	def test_receiving_stock_clears_the_temporary_flag(self):
		temp = self._create("Arrives Soon")["item_code"]
		bystander = make_item("AB-BYSTANDER").name
		frappe.db.set_value("Item", temp, "custom_approval_status", "Approved")

		make_stock_entry(item_code=temp, target=WAREHOUSE, qty=5, basic_rate=40, company=COMPANY)

		flags = frappe.db.get_value(
			"Item", temp, ["custom_is_temporary", "custom_temp_received_on"], as_dict=True
		)
		self.assertEqual(flags.custom_is_temporary, 0)
		self.assertIsNotNone(flags.custom_temp_received_on)
		self.assertEqual(frappe.db.get_value("Item", bystander, "custom_temp_received_on"), None)
		self.assertTrue(
			frappe.db.exists("Comment", {"reference_doctype": "Item", "reference_name": temp, "comment_type": "Info"})
		)

	def test_material_issue_does_not_clear_the_flag(self):
		temp = self._create("Still Temporary")["item_code"]
		frappe.db.set_value("Item", temp, "custom_approval_status", "Approved")
		make_stock_entry(item_code=temp, target=WAREHOUSE, qty=5, basic_rate=40, company=COMPANY)
		frappe.db.set_value("Item", temp, "custom_is_temporary", 1)

		make_stock_entry(item_code=temp, source=WAREHOUSE, qty=1, company=COMPANY)

		self.assertEqual(frappe.db.get_value("Item", temp, "custom_is_temporary"), 1)
