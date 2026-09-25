# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

"""PDC Allocation - cash position of receivable & payable post-dated cheques
with a running fund-in-bank balance.

Sourced the same way as PDC Register / PDC Bank Projection: a PDC is a
Payment Entry (Receive/Pay) against a Mode of Payment flagged
custom_is_pdc_payment. It never touches a real bank account directly - it
posts to that Mode of Payment's "Cheques in Hand" account, resolved via
Mode of Payment Account. Only once "Cleared/In Bank" (linked to a Payment
Entry/Journal Entry "Clearing Voucher" that is itself an Internal Transfer
out of Cheques in Hand) does money reach a real bank GL account - so a
Pending/In Bank cheque is exactly the set of PDCs not yet reflected in the
real bank balance, and no adjustment is needed on top of the GL opening
balance (unlike a vanilla ERPNext PDC-on-real-bank-account model).
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate

RECEIVABLE = "Receivable"
PAYABLE = "Payable"


def get_pdc_modes():
	"""Modes of Payment flagged as PDC via Mode of Payment.custom_is_pdc_payment."""
	return frappe.get_all("Mode of Payment", filters={"custom_is_pdc_payment": 1}, pluck="name")


def get_target_account(mode_of_payment, company, payment_type):
	"""Same "Cheques in Hand" account resolution used by al_buraq.api.pdc."""
	row = frappe.db.get_value(
		"Mode of Payment Account",
		{"parent": mode_of_payment, "company": company},
		["default_account", "custom_issued_account"],
		as_dict=True,
	)
	if not row:
		return None
	if payment_type == "Pay" and row.custom_issued_account:
		return row.custom_issued_account
	return row.default_account


def get_real_bank_account(cheques_in_hand_account, voucher_type, voucher_no):
	"""Given the "Cheques in Hand" leg of a clearing voucher, find the real bank
	GL account on the other leg. Only resolvable once a cheque is "In Bank" -
	a Pending cheque has no clearing voucher yet, so its eventual bank is unknown."""
	if voucher_type == "Payment Entry":
		pe = frappe.db.get_value("Payment Entry", voucher_no, ["paid_from", "paid_to"], as_dict=True)
		if pe:
			return pe.paid_to if pe.paid_from == cheques_in_hand_account else pe.paid_from
		return None
	if voucher_type == "Journal Entry":
		accounts = frappe.get_all("Journal Entry Account", filters={"parent": voucher_no}, pluck="account")
		return next((a for a in accounts if a != cheques_in_hand_account), None)
	return None


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	pdc_modes = get_pdc_modes()
	if not pdc_modes:
		frappe.throw(_("No Mode of Payment is flagged as PDC (Mode of Payment > Is PDC Payment)"))

	entries = get_payment_entries(filters, pdc_modes)
	banks = get_bank_accounts(filters, pdc_modes)
	opening = get_opening_balance(filters, banks)

	data, stats = build_rows(entries, opening, filters, currency)
	return get_columns(), data, None, get_chart(stats), get_summary(stats, currency)


# ---------------------------------------------------------------- filters
def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are mandatory"))
	filters.from_date = getdate(filters.from_date)
	filters.to_date = getdate(filters.to_date)
	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date cannot be after To Date"))
	filters.opening_date = add_days(filters.from_date, -1)
	filters.docstatus = (0, 1) if filters.get("include_draft") else (1,)


def get_cheques_in_hand_accounts(pdc_modes):
	"""Accounts a PDC-flagged Mode of Payment posts to before it reaches a real
	bank (al_buraq.setup.setup_pdc_config creates these with account_type=Bank
	too, so they must be excluded from the real-bank sweep below or a Pending/
	In Bank cheque's balance would be double-counted)."""
	if not pdc_modes:
		return set()
	rows = frappe.get_all(
		"Mode of Payment Account",
		filters={"parent": ["in", pdc_modes]},
		fields=["default_account", "custom_issued_account"],
	)
	accounts = set()
	for row in rows:
		accounts.update(a for a in (row.default_account, row.custom_issued_account) if a)
	return accounts


def get_bank_accounts(filters, pdc_modes):
	if filters.get("bank_gl_account"):
		return [filters.bank_gl_account]
	banks = frappe.get_all(
		"Account",
		filters={"company": filters.company, "account_type": "Bank", "is_group": 0, "disabled": 0},
		pluck="name",
	)
	exclude = get_cheques_in_hand_accounts(pdc_modes)
	return [b for b in banks if b not in exclude]


# ---------------------------------------------------------------- source
def get_payment_entries(filters, pdc_modes):
	conditions = {
		"company": filters.company,
		"docstatus": ["in", filters.docstatus],
		"mode_of_payment": ["in", pdc_modes],
		"payment_type": ["in", ["Receive", "Pay"]],
		"reference_date": ["<=", filters.to_date],
	}

	rows = frappe.get_all(
		"Payment Entry",
		filters=conditions,
		fields=[
			"name",
			"payment_type",
			"party_type",
			"party",
			"party_name",
			"reference_no",
			"reference_date",
			"paid_amount",
			"received_amount",
			"mode_of_payment",
			"docstatus",
			"custom_clearing_voucher_type",
			"custom_clearing_voucher_no",
		],
		order_by="reference_date asc",
	)
	rows = [r for r in rows if r.reference_no]
	if not rows:
		return []

	vouchers_by_type = {}
	for r in rows:
		if r.custom_clearing_voucher_type and r.custom_clearing_voucher_no:
			vouchers_by_type.setdefault(r.custom_clearing_voucher_type, set()).add(r.custom_clearing_voucher_no)

	clearance_by_voucher = {}
	for vtype, names in vouchers_by_type.items():
		for t in frappe.get_all(vtype, filters={"name": ["in", list(names)]}, fields=["name", "clearance_date"]):
			clearance_by_voucher[(vtype, t.name)] = t.clearance_date

	entries = []
	for r in rows:
		voucher_key = (r.custom_clearing_voucher_type, r.custom_clearing_voucher_no)
		if not r.custom_clearing_voucher_no:
			pdc_status = "Pending"
		elif clearance_by_voucher.get(voucher_key):
			pdc_status = "Cleared"
		else:
			pdc_status = "In Bank"

		# Cleared cheques have already reached, and been reconciled against, the
		# real bank balance - counting them here would double-count against the
		# opening balance/projection.
		if pdc_status == "Cleared":
			continue
		if filters.get("pdc_status") and pdc_status != filters.pdc_status:
			continue

		bank_gl_account = None
		if pdc_status == "In Bank":
			cheques_in_hand_account = get_target_account(r.mode_of_payment, filters.company, r.payment_type)
			if cheques_in_hand_account:
				bank_gl_account = get_real_bank_account(
					cheques_in_hand_account, r.custom_clearing_voucher_type, r.custom_clearing_voucher_no
				)

		# A Pending cheque has no clearing voucher yet, so which bank it will
		# eventually land in is not known - a bank filter is only meaningful for
		# In Bank rows.
		if filters.get("bank_gl_account"):
			if pdc_status == "Pending":
				continue
			if bank_gl_account != filters.bank_gl_account:
				continue

		is_receive = r.payment_type == "Receive"
		pdc_type = RECEIVABLE if is_receive else PAYABLE
		if filters.get("pdc_type") and pdc_type != filters.pdc_type:
			continue
		if filters.get("party_type") and r.party_type != filters.party_type:
			continue
		if filters.get("party") and r.party != filters.party:
			continue

		cheque_date = getdate(r.reference_date)
		if cheque_date < filters.from_date and not filters.get("include_overdue"):
			continue

		entries.append(
			frappe._dict(
				pdc_type=pdc_type,
				party_type=r.party_type,
				party=r.party,
				party_name=r.party_name or r.party,
				cheque_no=r.reference_no,
				cheque_date=cheque_date,
				amount=flt(r.received_amount) if is_receive else flt(r.paid_amount),
				cheque_status=pdc_status,
				voucher_type="Payment Entry",
				voucher_no=r.name,
			)
		)

	return entries


# ---------------------------------------------------------------- opening
def get_opening_balance(filters, banks):
	if filters.get("opening_balance") not in (None, ""):
		return flt(filters.opening_balance)
	if not banks:
		return 0.0

	return flt(
		frappe.db.sql(
			"""select sum(debit - credit) from `tabGL Entry`
			where account in %(banks)s and company = %(company)s
				and posting_date <= %(opening_date)s and is_cancelled = 0 and docstatus = 1""",
			dict(filters, banks=tuple(banks)),
		)[0][0]
	)


# ---------------------------------------------------------------- rows
def build_rows(entries, opening, filters, currency):
	for e in entries:
		e.overdue = e.cheque_date < filters.from_date
		e.due_date = filters.from_date if e.overdue else e.cheque_date
	entries.sort(key=lambda e: (e.due_date, 0 if e.pdc_type == RECEIVABLE else 1, e.cheque_no or ""))

	stats = frappe._dict(
		opening=opening,
		total_in=0.0,
		total_out=0.0,
		lowest=opening,
		lowest_date=filters.from_date,
		first_shortfall=None,
		months={},
	)
	data = [
		{
			"due_date": filters.from_date,
			"party_name": _("Opening Balance (as per bank)"),
			"running_balance": opening,
			"status": "Shortfall" if opening < 0 else "OK",
			"currency": currency,
			"row_type": "opening",
		}
	]
	if opening < 0:
		stats.first_shortfall = filters.from_date

	balance = opening
	month_key = None
	m_in = m_out = 0.0

	def month_total(key, m_in, m_out, bal):
		return {
			"party_name": _("Total - {0}").format(key),
			"receivable": m_in,
			"payable": m_out,
			"running_balance": bal,
			"currency": currency,
			"row_type": "total",
		}

	for e in entries:
		key = e.due_date.strftime("%b %Y")
		if month_key and key != month_key and filters.get("show_month_totals"):
			data.append(month_total(month_key, m_in, m_out, balance))
		if key != month_key:
			m_in = m_out = 0.0
			month_key = key
			stats.months.setdefault(key, frappe._dict(r=0.0, p=0.0, bal=0.0))

		inflow = e.amount if e.pdc_type == RECEIVABLE else 0.0
		outflow = e.amount if e.pdc_type == PAYABLE else 0.0
		balance += inflow - outflow
		m_in += inflow
		m_out += outflow
		stats.total_in += inflow
		stats.total_out += outflow
		stats.months[key].r += inflow
		stats.months[key].p += outflow
		stats.months[key].bal = balance
		if balance < stats.lowest:
			stats.lowest, stats.lowest_date = balance, e.due_date
		if balance < 0 and not stats.first_shortfall:
			stats.first_shortfall = e.due_date

		remarks = []
		if e.overdue:
			remarks.append(_("Overdue - cheque dated {0}").format(frappe.format(e.cheque_date, "Date")))

		data.append(
			{
				"due_date": e.due_date,
				"pdc_type": e.pdc_type,
				"party_type": e.party_type,
				"party": e.party,
				"party_name": e.party_name,
				"cheque_no": e.cheque_no,
				"cheque_date": e.cheque_date,
				"receivable": inflow,
				"payable": outflow,
				"running_balance": balance,
				"status": "Shortfall" if balance < 0 else "OK",
				"cheque_status": e.cheque_status,
				"voucher_type": e.voucher_type,
				"voucher_no": e.voucher_no,
				"remarks": "; ".join(remarks),
				"currency": currency,
			}
		)

	if month_key and filters.get("show_month_totals"):
		data.append(month_total(month_key, m_in, m_out, balance))

	data.append(
		{
			"party_name": _("Grand Total"),
			"receivable": stats.total_in,
			"payable": stats.total_out,
			"running_balance": balance,
			"currency": currency,
			"row_type": "total",
		}
	)
	stats.closing = balance
	return data, stats


# ---------------------------------------------------------------- output
def get_columns():
	return [
		{"label": _("Due Date"), "fieldname": "due_date", "fieldtype": "Date", "width": 100},
		{"label": _("Type"), "fieldname": "pdc_type", "fieldtype": "Data", "width": 95},
		{"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data", "width": 90},
		{"label": _("Party"), "fieldname": "party", "fieldtype": "Dynamic Link", "options": "party_type", "width": 150},
		{"label": _("Party Name"), "fieldname": "party_name", "fieldtype": "Data", "width": 220},
		{"label": _("Cheque No"), "fieldname": "cheque_no", "fieldtype": "Data", "width": 100},
		{"label": _("Cheque Date"), "fieldname": "cheque_date", "fieldtype": "Date", "width": 100},
		{"label": _("Receivable (In)"), "fieldname": "receivable", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Payable (Out)"), "fieldname": "payable", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Running Balance"), "fieldname": "running_balance", "fieldtype": "Currency", "options": "currency", "width": 140},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 90},
		{"label": _("PDC Status"), "fieldname": "cheque_status", "fieldtype": "Data", "width": 100},
		{"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 120},
		{"label": _("Voucher No"), "fieldname": "voucher_no", "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 160},
		{"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 240},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


def get_chart(stats):
	if not stats.months:
		return None
	labels = list(stats.months)
	return {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("Receivable"), "chartType": "bar", "values": [stats.months[m].r for m in labels]},
				{"name": _("Payable"), "chartType": "bar", "values": [stats.months[m].p for m in labels]},
				{"name": _("Closing Balance"), "chartType": "line", "values": [stats.months[m].bal for m in labels]},
			],
		},
		"type": "axis-mixed",
		"colors": ["#2E7D32", "#B5563A", "#1F2A44"],
		"fieldtype": "Currency",
	}


def get_summary(stats, currency):
	def cur(v, label, indicator):
		return {"value": v, "label": label, "datatype": "Currency", "currency": currency, "indicator": indicator}

	return [
		cur(stats.opening, _("Opening Balance"), "Blue"),
		cur(stats.total_in, _("PDC Receivable"), "Green"),
		cur(stats.total_out, _("PDC Payable"), "Red"),
		cur(stats.closing, _("Closing Balance"), "Green" if stats.closing >= 0 else "Red"),
		cur(stats.lowest, _("Lowest Balance"), "Green" if stats.lowest >= 0 else "Red"),
		{
			"value": stats.first_shortfall or _("None"),
			"label": _("First Shortfall"),
			"datatype": "Date" if stats.first_shortfall else "Data",
			"indicator": "Red" if stats.first_shortfall else "Green",
		},
		cur(max(0, -stats.lowest), _("Funding Required"), "Orange" if stats.lowest < 0 else "Green"),
	]
