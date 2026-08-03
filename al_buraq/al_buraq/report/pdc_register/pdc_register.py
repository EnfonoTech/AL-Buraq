import frappe
from frappe import _
from frappe.utils import flt, getdate


def get_pdc_modes():
	"""Modes of Payment flagged as PDC via Mode of Payment.custom_is_pdc_payment."""
	return frappe.get_all("Mode of Payment", filters={"custom_is_pdc_payment": 1}, pluck="name")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"fieldname": "reference_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{
			"fieldname": "payment_entry",
			"label": _("Payment Entry"),
			"fieldtype": "Link",
			"options": "Payment Entry",
			"width": 150,
		},
		{"fieldname": "reference_no", "label": _("Cheque No"), "fieldtype": "Data", "width": 110},
		{
			"fieldname": "party_type",
			"label": _("Party Type"),
			"fieldtype": "Link",
			"options": "DocType",
			"width": 100,
		},
		{
			"fieldname": "party",
			"label": _("Party"),
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 130,
		},
		{"fieldname": "party_name", "label": _("Party Name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "pdc_status", "label": _("PDC Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "payment_type", "label": _("Payment Type"), "fieldtype": "Data", "width": 100},
		{"fieldname": "direction", "label": _("Direction"), "fieldtype": "Data", "width": 90},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "width": 120},
		{
			"fieldname": "clearing_voucher",
			"label": _("Clearing Voucher"),
			"fieldtype": "Dynamic Link",
			"options": "clearing_voucher_type",
			"width": 170,
		},
		{
			"fieldname": "bank_gl_account",
			"label": _("Bank GL Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 170,
		},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
	]


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
	GL account on the other leg."""
	if voucher_type == "Payment Entry":
		pe = frappe.db.get_value(
			"Payment Entry", voucher_no, ["paid_from", "paid_to"], as_dict=True
		)
		if pe:
			return pe.paid_to if pe.paid_from == cheques_in_hand_account else pe.paid_from
		return None
	if voucher_type == "Journal Entry":
		accounts = frappe.get_all(
			"Journal Entry Account", filters={"parent": voucher_no}, pluck="account"
		)
		return next((a for a in accounts if a != cheques_in_hand_account), None)
	return None


def get_data(filters):
	pdc_modes = get_pdc_modes()
	if not pdc_modes:
		return []

	conditions = {
		"company": filters.company,
		"docstatus": ["!=", 2],
		"mode_of_payment": ["in", pdc_modes],
	}
	if filters.from_date and filters.to_date:
		conditions["reference_date"] = ["between", [filters.from_date, filters.to_date]]

	rows = frappe.get_all(
		"Payment Entry",
		filters=conditions,
		fields=[
			"name",
			"party_type",
			"party",
			"party_name",
			"reference_no",
			"reference_date",
			"paid_amount",
			"received_amount",
			"payment_type",
			"mode_of_payment",
			"docstatus",
			"custom_clearing_voucher_type",
			"custom_clearing_voucher_no",
		],
		order_by="reference_date desc",
	)

	# clearance_date lives on both Payment Entry and Journal Entry, but the two
	# name series can collide, so look each voucher type up separately.
	vouchers_by_type = {}
	for r in rows:
		if r.custom_clearing_voucher_type and r.custom_clearing_voucher_no:
			vouchers_by_type.setdefault(r.custom_clearing_voucher_type, set()).add(
				r.custom_clearing_voucher_no
			)

	clearance_by_voucher = {}
	for vtype, names in vouchers_by_type.items():
		for t in frappe.get_all(
			vtype, filters={"name": ["in", list(names)]}, fields=["name", "clearance_date"]
		):
			clearance_by_voucher[(vtype, t.name)] = t.clearance_date

	docstatus_label = {0: _("Draft"), 1: _("Submitted"), 2: _("Cancelled")}

	data = []
	for r in rows:
		is_received = r.payment_type == "Receive"
		amount = flt(r.received_amount) if is_received else flt(r.paid_amount)
		direction = _("Receivable") if is_received else _("Payable")

		voucher_key = (r.custom_clearing_voucher_type, r.custom_clearing_voucher_no)
		if not r.custom_clearing_voucher_no:
			pdc_status = _("Pending")
		elif clearance_by_voucher.get(voucher_key):
			pdc_status = _("Cleared")
		else:
			pdc_status = _("In Bank")

		# Pending cheques haven't touched any bank yet - only In Bank/Cleared
		# ones have a real bank account on the other leg of the clearing voucher.
		bank_gl_account = None
		if pdc_status != _("Pending"):
			cheques_in_hand_account = get_target_account(
				r.mode_of_payment, filters.company, r.payment_type
			)
			if cheques_in_hand_account:
				bank_gl_account = get_real_bank_account(
					cheques_in_hand_account, r.custom_clearing_voucher_type, r.custom_clearing_voucher_no
				)

		if filters.direction and direction != _(filters.direction):
			continue
		if filters.pdc_status and pdc_status != _(filters.pdc_status):
			continue
		if filters.payment_type and r.payment_type != filters.payment_type:
			continue
		if filters.bank_gl_account and bank_gl_account != filters.bank_gl_account:
			continue

		data.append(
			{
				"reference_date": getdate(r.reference_date) if r.reference_date else None,
				"payment_entry": r.name,
				"reference_no": r.reference_no,
				"party_type": r.party_type,
				"party": r.party,
				"party_name": r.party_name,
				"pdc_status": pdc_status,
				"payment_type": r.payment_type,
				"direction": direction,
				"amount": amount,
				"clearing_voucher": r.custom_clearing_voucher_no or "",
				"clearing_voucher_type": r.custom_clearing_voucher_type or "",
				"bank_gl_account": bank_gl_account or "",
				"status": docstatus_label.get(r.docstatus, ""),
			}
		)

	return data
