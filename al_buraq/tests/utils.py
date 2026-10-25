from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

COMPANY = "Al Buraq Test"
WAREHOUSE = "Stores - ABT"


class AlBuraqTestCase(FrappeTestCase):
	"""The approval scripts shipped with al_buraq are Server Scripts, which a bench only runs when
	server_script_enabled is set in common_site_config. Tests switch the check on for the run
	instead of changing the shared bench config."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._safe_exec_patch = patch("frappe.utils.safe_exec.is_safe_exec_enabled", return_value=True)
		cls._safe_exec_patch.start()
		cls.addClassCleanup(cls._safe_exec_patch.stop)


def ensure_company():
	if not frappe.db.exists("Company", COMPANY):
		frappe.throw(
			f"Test company {COMPANY} missing. Run the setup wizard on the test site first "
			"(see docs/batch1-requirements.md)."
		)


def make_customer(name="AB Test Customer"):
	if frappe.db.exists("Customer", name):
		return name
	frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": name,
			"customer_group": "Individual",
			"territory": "All Territories",
		}
	).insert(ignore_permissions=True)
	return name


def make_item(item_code, is_stock_item=1, valuation_rate=0, last_purchase_rate=0, stock_uom="Nos", **kwargs):
	if frappe.db.exists("Item", item_code):
		frappe.delete_doc("Item", item_code, force=True)
	doc = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": item_code,
			"item_name": item_code,
			"item_group": "All Item Groups",
			"stock_uom": stock_uom,
			"is_stock_item": is_stock_item,
			"valuation_rate": valuation_rate,
			"last_purchase_rate": last_purchase_rate,
			**kwargs,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def make_quotation(rows, submit=False):
	"""rows: list of dicts with item_code, qty, rate and optionally valuation_rate."""
	doc = frappe.new_doc("Quotation")
	doc.update(
		{
			"quotation_to": "Customer",
			"party_name": make_customer(),
			"company": COMPANY,
			"transaction_date": nowdate(),
			"valid_till": add_days(nowdate(), 30),
		}
	)
	for row in rows:
		doc.append("items", row)
	doc.insert(ignore_permissions=True)
	if submit:
		doc.submit()
	return doc


def make_user(email, roles):
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	user = frappe.get_doc(
		{"doctype": "User", "email": email, "first_name": "AB Test", "send_welcome_email": 0, "enabled": 1}
	)
	user.insert(ignore_permissions=True)
	user.add_roles(*roles)
	return user
