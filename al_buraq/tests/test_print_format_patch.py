from types import SimpleNamespace

import frappe
from frappe.tests.utils import FrappeTestCase

from al_buraq.patches import update_print_formats_batch1 as patch

QUOTATION_PRINT = """<html><head><style>.terms-box { margin-top: 15px; }</style></head>
<body>
<table class="main-table"><tbody><tr><td>
	<div>items here</div>
	<!-- TERMS AND CONDITIONS -->
	{% if doc.terms %}
	<div class="terms-box">
		<div class="terms-title">Terms and Conditions</div>
		<div class="terms-content">{{ doc.terms }}</div>
	</div>
	{% endif %}
	<!-- SIGNATURE -->
	<table class="sign-table"><tr><td>Authorized Signatory</td></tr></table>
</td></tr></tbody></table>
</body>
</html>"""

QUOTATION_PRINT_FORMAT = """<div class="invoice-wrapper">
	<table class="main-table"><tbody><tr><td>items here</td></tr></tbody></table>
</div>"""

QUOTATION_PF = """<html><body>
<table><tbody><tr><td>
	<div class="sign-table">signature</div>
	<div class="terms-box">
		<div class="terms-title">Terms and Conditions</div>
		<div class="terms-content">HARDCODED WORDING</div>
	</div>

	<!-- CLIENT ACCEPTANCE & ACKNOWLEDGEMENT -->
	<div class="accept-box">accept</div>
</td></tr></tbody></table>
</body></html>"""

SALES_INVOICE = """<table class="meta-table">
	<tr><td class="meta-key">Invoice#</td><td class="meta-val">{{ doc.name }}</td></tr>
	<tr><td class="meta-key">Sales person</td><td class="meta-val">x</td></tr>
</table>"""

SALES_ORDER = SALES_INVOICE.replace("Invoice#", "Proforma#")


class TestPrintFormatTransforms(FrappeTestCase):
	def test_terms_move_to_a_last_page_in_quotation_print(self):
		html = patch.transform_quotation_print(QUOTATION_PRINT)

		self.assertNotIn('<div class="terms-box">', html)
		self.assertIn("page-break-before: always", html)
		self.assertLess(html.index("Authorized Signatory"), html.index("al_buraq:tc-page"))
		self.assertEqual(html.count("{{ doc.terms }}"), 1)
		self.assertTrue(html.rstrip().endswith("</html>"))

	def test_terms_page_is_added_to_the_format_that_had_none(self):
		html = patch.transform_quotation_print_format(QUOTATION_PRINT_FORMAT)
		self.assertIn("{{ doc.terms }}", html)
		self.assertTrue(html.startswith('<div class="invoice-wrapper">'))

	def test_selected_terms_replace_the_hardcoded_wording(self):
		html = patch.transform_quotation_pf(QUOTATION_PF)

		with_terms = frappe.render_template(html, {"doc": frappe._dict(terms="CUSTOMER TERMS")})
		self.assertIn("CUSTOMER TERMS", with_terms)
		self.assertNotIn("HARDCODED WORDING", with_terms)
		self.assertIn("accept-box", with_terms)

		without_terms = frappe.render_template(html, {"doc": frappe._dict(terms="")})
		self.assertIn("HARDCODED WORDING", without_terms)
		self.assertIn("accept-box", without_terms)

	def test_terms_page_renders_only_when_the_quotation_has_terms(self):
		html = patch.transform_quotation_print(QUOTATION_PRINT)
		doc = frappe._dict(name="QTN-1", company="Al Buraq Test", terms="")

		self.assertNotIn("Terms and Conditions", frappe.render_template(html, {"doc": doc}))

		doc.terms = "PAY IN 30 DAYS"
		rendered = frappe.render_template(html, {"doc": doc})
		self.assertIn("Quotation QTN-1", rendered)
		self.assertIn("PAY IN 30 DAYS", rendered)

	def test_delivery_note_row_is_added_before_sales_person(self):
		html = patch.transform_sales_invoice(SALES_INVOICE)
		self.assertLess(html.index("al_buraq:dn-ref"), html.index("Sales person"))

		items = [
			frappe._dict(delivery_note="DN-1", sales_order=None),
			frappe._dict(delivery_note="DN-2", sales_order=None),
			frappe._dict(delivery_note="DN-1", sales_order=None),
		]
		rendered = frappe.render_template(html, {"doc": SimpleNamespace(name="SINV-1", items=items)})
		self.assertIn("Against Delivery Note", rendered)
		self.assertIn("DN-1, DN-2", rendered)

		bare = frappe.render_template(
			html, {"doc": SimpleNamespace(name="SINV-2", items=[frappe._dict(delivery_note=None, sales_order=None)])}
		)
		self.assertNotIn("Against Delivery Note", bare)

	def test_sales_order_delivery_note_row_renders_without_deliveries(self):
		html = patch.transform_sales_order(SALES_ORDER)
		rendered = frappe.render_template(html, {"doc": frappe._dict(name="SO-NOT-DELIVERED")})
		self.assertNotIn("Delivery Note", rendered)
		self.assertIn("Sales person", rendered)

	def test_every_transform_is_idempotent(self):
		cases = [
			(patch.transform_quotation_print, QUOTATION_PRINT),
			(patch.transform_quotation_print_format, QUOTATION_PRINT_FORMAT),
			(patch.transform_quotation_pf, QUOTATION_PF),
			(patch.transform_sales_invoice, SALES_INVOICE),
			(patch.transform_sales_order, SALES_ORDER),
		]
		for transform, source in cases:
			once = transform(source)
			self.assertEqual(transform(once), once, transform.__name__)

	def test_missing_anchor_returns_none(self):
		self.assertIsNone(patch.transform_quotation_print("<body>no terms block</body>"))
		self.assertIsNone(patch.transform_quotation_pf("<body>nothing</body>"))
		self.assertIsNone(patch.transform_sales_invoice("<table></table>"))


class TestPrintFormatPatchRun(FrappeTestCase):
	def _format(self, name, doc_type, html):
		if frappe.db.exists("Print Format", name):
			frappe.delete_doc("Print Format", name, force=True, ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Print Format",
				"name": name,
				"doc_type": doc_type,
				"module": "Selling",
				"standard": "No",
				"custom_format": 1,
				"print_format_type": "Jinja",
				"html": html,
			}
		).insert(ignore_permissions=True)

	def test_execute_updates_formats_once_and_skips_hand_edited_ones(self):
		self._format("Quotation Print", "Quotation", QUOTATION_PRINT)
		self._format("Tax Invoice Print Format", "Sales Invoice", SALES_INVOICE)
		self._format("Performa Invoice", "Sales Order", "<table>edited by hand, no anchor</table>")

		patch.execute()

		html = frappe.db.get_value("Print Format", "Quotation Print", "html")
		self.assertIn("al_buraq:tc-page", html)
		self.assertIn("al_buraq:dn-ref", frappe.db.get_value("Print Format", "Tax Invoice Print Format", "html"))
		self.assertEqual(
			frappe.db.get_value("Print Format", "Performa Invoice", "html"),
			"<table>edited by hand, no anchor</table>",
		)

		patch.execute()
		self.assertEqual(frappe.db.get_value("Print Format", "Quotation Print", "html"), html)

	def test_execute_ignores_formats_the_site_does_not_have(self):
		for name in patch.FORMATS:
			if frappe.db.exists("Print Format", name):
				frappe.delete_doc("Print Format", name, force=True, ignore_permissions=True)
		patch.execute()
