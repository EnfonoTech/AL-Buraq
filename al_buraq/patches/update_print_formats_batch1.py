import re

import frappe

TC_MARKER = "<!-- al_buraq:tc-page -->"
DN_MARKER = "{# al_buraq:dn-ref #}"

# Terms and Conditions on a page of their own, after the signature (requirement 2.1.1).
TC_PAGE = """
<!-- al_buraq:tc-page -->
{% if doc.terms %}
<div style="page-break-before: always; padding: 10px 14px; font-size: 11px; line-height: 1.5;">
	<div style="font-weight: bold; font-size: 13px; margin-bottom: 4px;">{{ doc.company }}</div>
	<div style="margin-bottom: 10px; color: #444;">Quotation {{ doc.name }} &mdash; Terms and Conditions</div>
	<div>{{ doc.terms }}</div>
</div>
{% endif %}
"""

# "Quotation PF" ships its own wording; the customer's selected terms replace it when present.
PF_TERMS_SELECTED = """{% if doc.terms %}
<div class="terms-box" style="page-break-before: always;">
	<div class="terms-title">Terms and Conditions</div>
	<div class="terms-content">{{ doc.terms }}</div>
</div>
{% else %}
"""

# Delivery Note reference row (requirement 2.2.3), same wording as the formats that already have it.
DN_ROW_SALES_INVOICE = """{# al_buraq:dn-ref #}
{%- set al_dn_so = doc.items | map(attribute="sales_order") | select | unique | list -%}
{%- set al_dn_ns = namespace(list=(doc.items | map(attribute="delivery_note") | select | unique | list)) -%}
{%- for so_name in al_dn_so -%}
	{%- for row in frappe.get_all("Delivery Note Item", filters={"against_sales_order": so_name, "docstatus": 1}, fields=["parent"], distinct=True) -%}
		{%- if row.parent and row.parent not in al_dn_ns.list -%}
			{%- set al_dn_ns.list = al_dn_ns.list + [row.parent] -%}
		{%- endif -%}
	{%- endfor -%}
{%- endfor -%}
{% if al_dn_ns.list %}<tr><td class="meta-key">Against Delivery Note</td><td class="meta-val">{{ al_dn_ns.list | join(", ") }}</td></tr>{% endif %}
"""

DN_ROW_SALES_ORDER = """{# al_buraq:dn-ref #}
{%- set al_dn_ns = namespace(list=[]) -%}
{%- for row in frappe.get_all("Delivery Note Item", filters={"against_sales_order": doc.name, "docstatus": 1}, fields=["parent"], distinct=True) -%}
	{%- if row.parent not in al_dn_ns.list -%}
		{%- set al_dn_ns.list = al_dn_ns.list + [row.parent] -%}
	{%- endif -%}
{%- endfor -%}
{% if al_dn_ns.list %}<tr><td class="meta-key">Delivery Note</td><td class="meta-val">{{ al_dn_ns.list | join(", ") }}</td></tr>{% endif %}
"""

SALES_PERSON_ROW = '<tr><td class="meta-key">Sales person</td>'


def transform_quotation_print(html):
	"""Move the inline terms block of "Quotation Print" to its own last page."""
	if TC_MARKER in html:
		return html

	inline = re.compile(
		r"[ \t]*<!-- TERMS AND CONDITIONS -->\s*\{% if doc\.terms %\}.*?\{% endif %\}[ \t]*\n?", re.S
	)
	if not inline.search(html):
		return None
	html = inline.sub("", html, count=1)
	return _append_before_body_end(html, TC_PAGE)


def transform_quotation_print_format(html):
	"""Add the terms page to "Quotation Print Format", which has no terms at all."""
	if TC_MARKER in html:
		return html
	return html.rstrip("\n") + "\n" + TC_PAGE


def transform_quotation_pf(html):
	"""Let the selected customer terms replace the hardcoded block of "Quotation PF"."""
	if TC_MARKER in html:
		return html

	start = html.find('<div class="terms-box">')
	end = html.find("<!-- CLIENT ACCEPTANCE")
	if start == -1 or end == -1 or start > end:
		return None

	hardcoded = html[start:end].rstrip()
	return html[:start] + TC_MARKER + "\n" + PF_TERMS_SELECTED + hardcoded + "\n{% endif %}\n\n" + html[end:]


def transform_sales_invoice(html):
	return _insert_dn_row(html, DN_ROW_SALES_INVOICE)


def transform_sales_order(html):
	return _insert_dn_row(html, DN_ROW_SALES_ORDER)


def _insert_dn_row(html, snippet):
	if DN_MARKER in html:
		return html
	at = html.find(SALES_PERSON_ROW)
	if at == -1:
		return None
	return html[:at] + snippet + html[at:]


def _append_before_body_end(html, block):
	at = html.rfind("</body>")
	if at == -1:
		return html.rstrip("\n") + "\n" + block
	return html[:at] + block + html[at:]


FORMATS = {
	"Quotation Print": transform_quotation_print,
	"Quotation Print Format": transform_quotation_print_format,
	"Quotation PF": transform_quotation_pf,
	"Tax Invoice Print Format": transform_sales_invoice,
	"Performa Invoice": transform_sales_order,
}


def execute():
	"""2.1.1 Terms and Conditions page on every Quotation print format, and 2.2.3 Delivery Note
	reference on the Sales Invoice / Sales Order formats that lacked it. Each edit is idempotent
	(marker comment) and skipped, with a log line, when the format no longer has the expected
	anchor, so a hand-edited format is never mangled. Back the site up before migrating: the
	previous HTML is not kept."""
	for name, transform in FORMATS.items():
		if not frappe.db.exists("Print Format", name):
			continue

		html = frappe.db.get_value("Print Format", name, "html")
		if not html:
			continue

		new_html = transform(html)
		if new_html is None:
			frappe.logger("al_buraq").warning(f"Print Format {name}: expected anchor not found, left unchanged")
			continue
		if new_html != html:
			frappe.db.set_value("Print Format", name, "html", new_html)
