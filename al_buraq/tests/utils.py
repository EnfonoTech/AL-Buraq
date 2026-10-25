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
	if not frappe.db.exists("Customer", name):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_group": "Individual",
				"territory": "All Territories",
			}
		).insert(ignore_permissions=True)
	# invoices are refused for a customer still awaiting credit-limit approval
	frappe.db.set_value("Customer", name, "custom_approval_status", "Approved")
	return name


def make_item(item_code, is_stock_item=1, valuation_rate=0, last_purchase_rate=0, stock_uom="Nos", approved=False, **kwargs):
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
	if approved:
		# straight to the table: the Item Approval workflow only lets a manager move Pending to Approved
		frappe.db.set_value("Item", doc.name, "custom_approval_status", "Approved")
		doc.reload()
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


def make_supplier(name="AB Test Supplier"):
	if frappe.db.exists("Supplier", name):
		return name
	frappe.get_doc({"doctype": "Supplier", "supplier_name": name, "supplier_group": "Local"}).insert(
		ignore_permissions=True
	)
	return name


def make_purchase_receipt(supplier, item_code, qty, rate):
	doc = frappe.get_doc(
		{
			"doctype": "Purchase Receipt",
			"company": COMPANY,
			"supplier": supplier,
			"posting_date": nowdate(),
			"items": [{"item_code": item_code, "qty": qty, "rate": rate, "warehouse": WAREHOUSE}],
		}
	)
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc


def ensure_sales_person_field():
	"""The live site has a Sales Person link on Sales Invoice that was added by hand."""
	if frappe.get_meta("Sales Invoice").has_field("custom_sales_person"):
		return
	frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": "Sales Invoice",
			"fieldname": "custom_sales_person",
			"label": "Sales Person",
			"fieldtype": "Link",
			"options": "Sales Person",
			"insert_after": "customer",
		}
	).insert(ignore_permissions=True)
	frappe.clear_cache(doctype="Sales Invoice")


def make_sales_person(name):
	if frappe.db.exists("Sales Person", name):
		return name
	frappe.get_doc({"doctype": "Sales Person", "sales_person_name": name, "parent_sales_person": "Sales Team"}).insert(
		ignore_permissions=True
	)
	return name


def make_sales_invoice(item_code, qty, rate, posting_date=None, sales_person=None, team_member=None, customer=None):
	"""Submitted Sales Invoice for a non-stock item. sales_person fills the Sales Person field,
	team_member fills the Sales Team table instead."""
	doc = frappe.new_doc("Sales Invoice")
	doc.update(
		{
			"company": COMPANY,
			"customer": customer or make_customer(),
			"posting_date": posting_date or nowdate(),
			"set_posting_time": 1,
			"custom_sales_person": sales_person,
		}
	)
	doc.append("items", {"item_code": item_code, "qty": qty, "rate": rate})
	if team_member:
		doc.append("sales_team", {"sales_person": team_member, "allocated_percentage": 100})
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc


def make_employee(user, reports_to=None, first_name="AB Employee"):
	"""Active employee tied to a user, optionally reporting to another employee."""
	existing = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": first_name,
			"gender": "Male",
			"date_of_birth": "1990-01-01",
			"date_of_joining": "2020-01-01",
			"company": COMPANY,
			"status": "Active",
			"user_id": user,
			"reports_to": reports_to,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def make_opportunity(owner="Administrator", days_old=0, status="Open", customer=None):
	"""Enquiry for a customer, created `days_old` days ago and owned by `owner`."""
	doc = frappe.get_doc(
		{
			"doctype": "Opportunity",
			"opportunity_from": "Customer",
			"party_name": customer or make_customer(),
			"company": COMPANY,
			"status": status,
			"opportunity_type": "Sales",
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.db.set_value(
		"Opportunity",
		doc.name,
		{"owner": owner, "creation": add_days(nowdate(), -days_old)},
		update_modified=False,
	)
	doc.reload()
	return doc


def bells(user):
	"""Subjects of the notifications a user has received today."""
	return frappe.get_all("Notification Log", filters={"for_user": user}, pluck="subject")
