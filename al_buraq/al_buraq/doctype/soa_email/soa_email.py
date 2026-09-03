# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.desk.query_report import run as run_query_report
from frappe.model.document import Document
from frappe.utils import flt, fmt_money, formatdate, nowdate
from frappe.utils.pdf import get_pdf


class SOAEmail(Document):
	pass


def _default_print_format(doctype, _cache={}):
	# "Standard" is a valid argument to frappe.get_print() (falls back to the
	# auto-generated layout) but is NOT an actual Print Format record for most
	# doctypes, so it can't be stored in a Link field - leave it blank instead
	# and let frappe.get_print() apply that same fallback at send time.
	if doctype not in _cache:
		_cache[doctype] = frappe.get_meta(doctype).default_print_format or ""
	return _cache[doctype]


@frappe.whitelist()
def get_print_formats_for_doctype(doctype=None, txt=None, searchfield=None, start=0, page_len=20, filters=None):
	# Print Format's own read permission is restricted to System Manager on
	# this site, so the row-level "print_format" Link field's default query
	# returns nothing for any other role even though matching records exist -
	# this custom query method is used instead (via frm.set_query's "query"
	# option) to deliberately bypass that and let any user pick a print
	# format for the document they're already allowed to see/attach.
	target_doctype = (filters or {}).get("doc_type") if filters else None
	if not target_doctype:
		return []

	pf_filters = {"doc_type": target_doctype, "disabled": 0}
	if txt:
		pf_filters["name"] = ["like", f"%{txt}%"]

	rows = frappe.get_all(
		"Print Format",
		filters=pf_filters,
		fields=["name"],
		limit_start=start,
		limit_page_length=page_len,
		order_by="name",
		ignore_permissions=True,
	)
	return [(r.name,) for r in rows]


@frappe.whitelist()
def get_transactions(party_type, party, from_date, to_date, company=None):
	result = []

	if party_type == "Customer":
		si_filters = {
			"customer": party,
			"posting_date": ["between", [from_date, to_date]],
			"docstatus": 1,
		}
		if company:
			si_filters["company"] = company

		invoices = frappe.get_all(
			"Sales Invoice",
			filters=si_filters,
			fields=["name"],
		)

		for inv in invoices:
			result.append(
				{
					"reference_type": "Sales Invoice",
					"reference_name": inv.name,
					"parent_invoice": inv.name,
					"include_in_email": 1,
					"print_format": _default_print_format("Sales Invoice"),
				}
			)

			si_items = frappe.get_all(
				"Sales Invoice Item",
				filters={"parent": inv.name},
				fields=["sales_order", "delivery_note"],
			)

			sales_orders = list({d.sales_order for d in si_items if d.sales_order})
			delivery_notes = list({d.delivery_note for d in si_items if d.delivery_note})

			quotations = []
			if sales_orders:
				so_items = frappe.get_all(
					"Sales Order Item",
					filters={"parent": ["in", sales_orders]},
					fields=["prevdoc_docname"],
				)
				quotations = list({d.prevdoc_docname for d in so_items if d.prevdoc_docname})

			for so in sales_orders:
				result.append(
					{
						"reference_type": "Sales Order",
						"reference_name": so,
						"parent_invoice": inv.name,
						"include_in_email": 0,
						"print_format": _default_print_format("Sales Order"),
					}
				)

			for dn in delivery_notes:
				result.append(
					{
						"reference_type": "Delivery Note",
						"reference_name": dn,
						"parent_invoice": inv.name,
						"include_in_email": 0,
						"print_format": _default_print_format("Delivery Note"),
					}
				)

			for qtn in quotations:
				result.append(
					{
						"reference_type": "Quotation",
						"reference_name": qtn,
						"parent_invoice": inv.name,
						"include_in_email": 0,
						"print_format": _default_print_format("Quotation"),
					}
				)
	else:
		pi_filters = {
			"supplier": party,
			"posting_date": ["between", [from_date, to_date]],
			"docstatus": 1,
		}
		if company:
			pi_filters["company"] = company

		invoices = frappe.get_all(
			"Purchase Invoice",
			filters=pi_filters,
			fields=["name"],
		)

		for inv in invoices:
			result.append(
				{
					"reference_type": "Purchase Invoice",
					"reference_name": inv.name,
					"parent_invoice": inv.name,
					"include_in_email": 1,
					"print_format": _default_print_format("Purchase Invoice"),
				}
			)

			pi_items = frappe.get_all(
				"Purchase Invoice Item",
				filters={"parent": inv.name},
				fields=["purchase_order"],
			)

			purchase_orders = list({d.purchase_order for d in pi_items if d.purchase_order})

			for po in purchase_orders:
				result.append(
					{
						"reference_type": "Purchase Order",
						"reference_name": po,
						"parent_invoice": inv.name,
						"include_in_email": 0,
						"print_format": _default_print_format("Purchase Order"),
					}
				)

	return result


def get_soa_statement_pdf(doc):
	"""Render the linked SOA report as a PDF for the selected party/date range.

	If `soa_print_format` is set and is a Jinja-type Report Print Format, its
	`html` is rendered server-side with a prepared context (aged-receivables
	style: party details, per-row running balance, aging totals). Report-type
	Print Formats of type "JS" run client-side only (no server-side Frappe API
	reproduces that) and are not usable here - fall back to a plain table in
	that case, or when no print format is selected at all.
	"""
	if not doc.soa_report:
		return None

	filters = {
		"company": doc.company,
		"from_date": doc.from_date,
		"to_date": doc.to_date,
		# "Accounts Receivable"/"Accounts Payable" use a single as-of date
		# (report_date) instead of from_date/to_date - without this they
		# default report_date to today and silently show 0 rows whenever
		# the party's invoices for the requested period are already settled.
		"report_date": doc.to_date,
		"party_type": doc.party_type,
		"party": [doc.party],
	}

	report_data = run_query_report(report_name=doc.soa_report, filters=filters)
	columns = report_data.get("columns", [])
	raw_rows = report_data.get("result", [])

	if doc.soa_print_format:
		pf = frappe.get_doc("Print Format", doc.soa_print_format)
		if pf.print_format_type == "Jinja" and pf.html:
			return _render_print_format_statement(doc, pf, filters, raw_rows)

	return _render_generic_statement_pdf(doc, filters, columns, raw_rows)


def _get_company_header_context(doc):
	if not doc.company:
		return {
			"company_logo": None,
			"company_display_name": doc.company or "",
			"company_tax_id": "",
			"company_address_lines": [],
		}

	company = frappe.db.get_value(
		"Company", doc.company, ["company_logo", "tax_id", "phone_no", "email", "website"], as_dict=True
	) or {}

	address_lines = []
	if company.get("phone_no"):
		address_lines.append(f"Tel {company['phone_no']}")
	if company.get("email"):
		address_lines.append(company["email"])
	if company.get("website"):
		address_lines.append(company["website"])

	return {
		"company_logo": company.get("company_logo"),
		"company_display_name": doc.company,
		"company_tax_id": company.get("tax_id") or "",
		"company_address_lines": address_lines,
	}


def _get_party_context(doc):
	if not doc.party:
		return {"party_name": "", "party_address": "", "party_tax_id": ""}

	field_map = {
		"Customer": ["customer_name", "tax_id", "customer_primary_address"],
		"Supplier": ["supplier_name", "tax_id", "supplier_primary_address"],
	}
	fields = field_map.get(doc.party_type)
	if not fields:
		return {"party_name": doc.party, "party_address": "", "party_tax_id": ""}

	pdata = frappe.db.get_value(doc.party_type, doc.party, fields, as_dict=True) or {}
	party_name = pdata.get("customer_name") or pdata.get("supplier_name") or doc.party
	party_tax_id = pdata.get("tax_id") or ""

	address_name = pdata.get("customer_primary_address") or pdata.get("supplier_primary_address")
	party_address = ""
	if address_name:
		adata = frappe.db.get_value(
			"Address",
			address_name,
			["address_line1", "address_line2", "city", "state", "country", "pincode"],
			as_dict=True,
		) or {}
		parts = [
			adata.get(key)
			for key in ("address_line1", "address_line2", "city", "state", "pincode", "country")
			if adata.get(key)
		]
		party_address = ", ".join(parts)

	return {"party_name": party_name, "party_address": party_address, "party_tax_id": party_tax_id}


def _money(value):
	return fmt_money(flt(value))


def _render_print_format_statement(doc, pf, filters, raw_rows):
	dict_rows = [r for r in raw_rows if isinstance(r, dict) and r.get("voucher_no")]

	pe_names = [r["voucher_no"] for r in dict_rows if r.get("voucher_type") == "Payment Entry"]
	si_names = [r["voucher_no"] for r in dict_rows if r.get("voucher_type") == "Sales Invoice"]

	pe_map = {}
	if pe_names:
		for pe in frappe.get_all("Payment Entry", filters={"name": ["in", pe_names]}, fields=["name", "payment_type"]):
			pe_map[pe.name] = pe.payment_type or ""

	si_map = {}
	if si_names:
		for si in frappe.get_all("Sales Invoice", filters={"name": ["in", si_names]}, fields=["name", "po_no", "is_return"]):
			si_map[si.name] = {"po_no": si.po_no or "", "is_return": si.is_return}

	currency = frappe.db.get_value("Company", doc.company, "default_currency") if doc.company else None
	currency = currency or "AED"

	rows = []
	t_amount = t_adjusted = t_balance = 0
	t_r1 = t_r2 = t_r3 = t_r4 = t_r5 = 0
	cum_bal = 0

	for row in dict_rows:
		amount = flt(row.get("invoiced")) - flt(row.get("credit_note"))
		adjusted = flt(row.get("paid"))
		balance = flt(row.get("outstanding"))
		cum_bal += balance

		t_amount += amount
		t_adjusted += adjusted
		t_balance += balance
		t_r1 += flt(row.get("range1"))
		t_r2 += flt(row.get("range2"))
		t_r3 += flt(row.get("range3"))
		t_r4 += flt(row.get("range4"))
		t_r5 += flt(row.get("range5"))

		voucher_type = row.get("voucher_type") or ""
		voucher_no = row["voucher_no"]
		if voucher_type == "Sales Invoice":
			si_info = si_map.get(voucher_no, {})
			type_label = "CRN" if si_info.get("is_return") else "INV"
			lpo = si_info.get("po_no") or ""
		elif voucher_type == "Payment Entry":
			type_label = pe_map.get(voucher_no) or "PE"
			lpo = ""
		else:
			type_label = voucher_type
			lpo = ""

		rows.append(
			{
				"posting_date_display": formatdate(row.get("posting_date")) if row.get("posting_date") else "-",
				"type_label": type_label,
				"voucher_no": voucher_no,
				"lpo": lpo,
				"amount_display": _money(amount),
				"adjusted_display": _money(adjusted),
				"balance_display": _money(balance),
				"cum_bal_display": _money(cum_bal),
				"age": row.get("age"),
			}
		)

	totals = {
		"amount_display": _money(t_amount),
		"adjusted_display": _money(t_adjusted),
		"balance_display": _money(t_balance),
		"cum_bal_display": _money(cum_bal),
		"range1_display": _money(t_r1),
		"range2_display": _money(t_r2),
		"range3_display": _money(t_r3),
		"range4_display": _money(t_r4),
		"range5_display": _money(t_r5),
		"overdue_display": _money(t_r1 + t_r2 + t_r3 + t_r4 + t_r5),
	}

	context = {
		"filters": filters,
		"currency": currency,
		"report_title": doc.soa_report,
		"as_of_date": formatdate(doc.to_date) if doc.to_date else formatdate(nowdate()),
		"generated_on": formatdate(nowdate()),
		"rows": rows,
		"totals": totals,
	}
	context.update(_get_company_header_context(doc))
	context.update(_get_party_context(doc))

	html = frappe.render_template(pf.html, context)
	return get_pdf(html)


def _render_generic_statement_pdf(doc, filters, columns, raw_rows):
	# Script Reports sometimes mix dict rows (normal data) with plain
	# list/tuple rows (e.g. a positional "Total" row) in the same result -
	# normalize everything to a fieldname-keyed dict so the template can
	# always do a plain key lookup.
	rows = []
	for row in raw_rows:
		if isinstance(row, dict):
			rows.append({col["fieldname"]: row.get(col["fieldname"], "") for col in columns})
		elif isinstance(row, (list, tuple)):
			rows.append(
				{col["fieldname"]: (row[idx] if idx < len(row) else "") for idx, col in enumerate(columns)}
			)

	html = frappe.render_template(
		"""
		<style>
			body { font-family: Arial, sans-serif; }
			table { border-collapse: collapse; width: 100%; table-layout: fixed; }
			th, td {
				font-size: 8px;
				padding: 3px;
				word-wrap: break-word;
				overflow-wrap: break-word;
			}
			th { background-color: #f2f2f2; text-align: left; }
		</style>
		<h2>Statement of Account</h2>
		<p><strong>{{ party_label }}:</strong> {{ party }}</p>
		<p><strong>Company:</strong> {{ company }}</p>
		<p><strong>Period:</strong> {{ from_date }} to {{ to_date }}</p>

		<table border="1" cellspacing="0">
			<tr>
				{% for column in columns %}
				<th>{{ column.label or column.fieldname }}</th>
				{% endfor %}
			</tr>
			{% for row in rows %}
			<tr>
				{% for column in columns %}
				<td>{{ row[column.fieldname] if row[column.fieldname] is not none else "" }}</td>
				{% endfor %}
			</tr>
			{% endfor %}
		</table>
		""",
		{
			"party_label": doc.party_type,
			"party": doc.party,
			"company": doc.company,
			"from_date": doc.from_date,
			"to_date": doc.to_date,
			"columns": columns,
			"rows": rows,
		},
	)

	return get_pdf(html, options={"orientation": "Landscape", "page-size": "A3"})


def get_letter_head_html(doc):
	letter_head_name = doc.letter_head

	if not letter_head_name and doc.company:
		letter_head_name = frappe.db.get_value("Company", doc.company, "default_letter_head")

	if not letter_head_name:
		return ""

	letter_head = frappe.get_cached_doc("Letter Head", letter_head_name)
	if letter_head.content:
		return letter_head.content
	if letter_head.image:
		return f'<img src="{letter_head.image}" style="max-width: 250px;"><br>'

	return ""


def get_email_subject_and_message(doc):
	if doc.email_template:
		formatted = frappe.get_doc("Email Template", doc.email_template).get_formatted_email(doc.as_dict())
		subject = formatted["subject"]
		message = formatted["message"]
	else:
		subject = _("Statement of Account - {0}").format(doc.party)
		message = _("Please find attached your Statement of Account and related documents.")

	if doc.subject:
		subject = frappe.render_template(doc.subject, doc.as_dict())

	return subject, get_letter_head_html(doc) + message


def build_soa_attachments(doc):
	attachments = []

	soa_pdf = get_soa_statement_pdf(doc)
	if soa_pdf:
		attachments.append(
			{
				"fname": f"SOA-{doc.party}.pdf",
				"fcontent": soa_pdf,
			}
		)

	for row in doc.transactions:
		if row.include_in_email:
			pdf_content = frappe.get_print(
				row.reference_type, row.reference_name, print_format=row.print_format, as_pdf=True
			)
			attachments.append(
				{
					"fname": f"{row.reference_type}-{row.reference_name}.pdf",
					"fcontent": pdf_content,
				}
			)

	return attachments


def _get_included_documents_html(doc):
	items = []
	if doc.soa_report:
		items.append(_("Statement of Account ({0})").format(doc.soa_report))

	for row in doc.transactions:
		if row.include_in_email:
			items.append(f"{row.reference_type} - {row.reference_name}")

	if not items:
		return ""

	list_html = "".join(f"<li>{frappe.utils.escape_html(item)}</li>" for item in items)
	return f"<p><strong>{_('Documents included in this email')}:</strong></p><ul>{list_html}</ul>"


def send_soa_email(doc):
	if not doc.email_to:
		frappe.throw(_("Email To is not set"))

	attachments = build_soa_attachments(doc)
	if not attachments:
		frappe.throw(_("No documents selected to send"))

	subject, message = get_email_subject_and_message(doc)
	message += _get_included_documents_html(doc)

	cc = [addr.strip() for addr in (doc.cc or "").split(",") if addr.strip()]

	if doc.sender:
		sender_email = frappe.db.get_value("Email Account", doc.sender, "email_id")
	else:
		sender_email = frappe.session.user

	frappe.enqueue(
		queue="short",
		method=frappe.sendmail,
		recipients=[doc.email_to],
		sender=sender_email,
		cc=cc,
		subject=subject,
		message=message,
		now=True,
		reference_doctype="SOA Email",
		reference_name=doc.name,
		attachments=attachments,
		expose_recipients="header",
	)

	return len(attachments)


@frappe.whitelist()
def send_email(docname):
	doc = frappe.get_doc("SOA Email", docname)
	attachment_count = send_soa_email(doc)
	return _("Email sent successfully with {0} attachment(s)").format(attachment_count)


@frappe.whitelist()
def send_bulk_emails(docnames):
	if isinstance(docnames, str):
		docnames = frappe.parse_json(docnames)

	sent = []
	failed = []

	for docname in docnames:
		try:
			doc = frappe.get_doc("SOA Email", docname)
			send_soa_email(doc)
			sent.append(docname)
		except Exception:
			failed.append({"docname": docname, "error": frappe.get_traceback()})
			frappe.log_error(title="SOA Bulk Email Failed", reference_doctype="SOA Email", reference_name=docname)

	return {"sent": sent, "failed": failed}
