"""Requirement 1.2 is standard ERPNext behaviour. This pins it down: the same call the
"Get Items From > Purchase Receipt" dialog makes, with several receipts, gives one Purchase
Invoice for one supplier."""

import json

import frappe
from frappe.model.mapper import map_docs

from al_buraq.tests.utils import (
	AlBuraqTestCase,
	ensure_company,
	make_item,
	make_purchase_receipt,
	make_supplier,
)

METHOD = "erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_purchase_invoice"


class TestConsolidatedPurchaseInvoice(AlBuraqTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_company()

	def test_one_invoice_from_several_receipts_of_the_same_supplier(self):
		supplier = make_supplier("AB Test Supplier")
		make_item("AB-PI-1")
		make_item("AB-PI-2")
		first = make_purchase_receipt(supplier, "AB-PI-1", 5, 10)
		second = make_purchase_receipt(supplier, "AB-PI-2", 3, 20)

		invoice = frappe.get_doc(map_docs(METHOD, json.dumps([first.name, second.name]), {}))
		invoice.insert(ignore_permissions=True)

		self.assertEqual(invoice.supplier, supplier)
		self.assertEqual(
			sorted((d.item_code, d.purchase_receipt) for d in invoice.items),
			[("AB-PI-1", first.name), ("AB-PI-2", second.name)],
		)
		self.assertEqual(invoice.total, 5 * 10 + 3 * 20)

	def test_the_receipt_is_marked_billed_once_its_invoice_is_submitted(self):
		supplier = make_supplier("AB Test Supplier")
		make_item("AB-PI-3")
		receipt = make_purchase_receipt(supplier, "AB-PI-3", 2, 15)

		invoice = frappe.get_doc(map_docs(METHOD, json.dumps([receipt.name]), {}))
		invoice.insert(ignore_permissions=True)
		invoice.submit()

		self.assertEqual(frappe.db.get_value("Purchase Receipt", receipt.name, "per_billed"), 100)
