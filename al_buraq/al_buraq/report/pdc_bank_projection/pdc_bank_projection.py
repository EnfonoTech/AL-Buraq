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
		{"fieldname": "reference_date", "label": _("Cheque Date"), "fieldtype": "Date", "width": 100},
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
		{"fieldname": "party_name", "label": _("Particulars"), "fieldtype": "Data", "width": 320},
		{"fieldname": "pdc_status", "label": _("PDC Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "direction", "label": _("Direction"), "fieldtype": "Data", "width": 90},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "width": 130},
		{
			"fieldname": "bank_gl_account",
			"label": _("Bank GL Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 170,
		},
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
	GL account on the other leg. Only resolvable once a cheque is "In Bank" -
	a Pending cheque has no clearing voucher yet, so its eventual bank is unknown."""
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
	if not pdc_modes or not filters.as_of_date:
		return []

	conditions = {
		"company": filters.company,
		"docstatus": ["!=", 2],
		"mode_of_payment": ["in", pdc_modes],
		"payment_type": ["in", ["Receive", "Pay"]],
		"reference_date": ["<=", filters.as_of_date],
	}

	rows = frappe.get_all(
		"Payment Entry",
		filters=conditions,
		fields=[
			"party_type",
			"party",
			"party_name",
			"reference_no",
			"reference_date",
			"paid_amount",
			"received_amount",
			"payment_type",
			"mode_of_payment",
			"custom_clearing_voucher_type",
			"custom_clearing_voucher_no",
		],
		order_by="reference_date asc",
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

	data = []
	pending_issued = 0.0
	pending_received = 0.0
	# In Bank totals are tracked per real bank GL account, since that's known
	# only once a cheque has an Internal Transfer clearing voucher.
	bank_totals = {}  # bank_gl_account -> {"issued": x, "received": x}

	for r in rows:
		voucher_key = (r.custom_clearing_voucher_type, r.custom_clearing_voucher_no)
		if not r.custom_clearing_voucher_no:
			pdc_status = _("Pending")
		elif clearance_by_voucher.get(voucher_key):
			pdc_status = _("Cleared")
		else:
			pdc_status = _("In Bank")

		# Cleared cheques are already reflected in the real bank balance - counting
		# them here would double-count against the projection.
		if pdc_status == _("Cleared"):
			continue
		if filters.pdc_status and pdc_status != _(filters.pdc_status):
			continue

		# A Pending cheque has no clearing voucher yet, so which bank it will
		# eventually land in is not known - only "In Bank" cheques resolve one.
		# A bank filter is only meaningful for those, so Pending is excluded
		# entirely once a bank filter is applied.
		if pdc_status == _("Pending") and filters.bank_gl_account:
			continue

		bank_gl_account = None
		if pdc_status != _("Pending"):
			cheques_in_hand_account = get_target_account(r.mode_of_payment, filters.company, r.payment_type)
			if cheques_in_hand_account:
				bank_gl_account = get_real_bank_account(
					cheques_in_hand_account, r.custom_clearing_voucher_type, r.custom_clearing_voucher_no
				)
			if filters.bank_gl_account and bank_gl_account != filters.bank_gl_account:
				continue

		is_received = r.payment_type == "Receive"
		amount = flt(r.received_amount) if is_received else flt(r.paid_amount)
		direction = _("Receivable") if is_received else _("Payable")

		if pdc_status == _("Pending"):
			if is_received:
				pending_received += amount
			else:
				pending_issued += amount
		else:
			bucket = bank_totals.setdefault(bank_gl_account or _("Unknown Bank"), {"issued": 0.0, "received": 0.0})
			if is_received:
				bucket["received"] += amount
			else:
				bucket["issued"] += amount

		data.append(
			{
				"reference_date": getdate(r.reference_date) if r.reference_date else None,
				"reference_no": r.reference_no,
				"party_type": r.party_type,
				"party": r.party,
				"party_name": r.party_name,
				"pdc_status": pdc_status,
				"direction": direction,
				"amount": amount,
				"bank_gl_account": bank_gl_account or "",
			}
		)

	in_bank_issued = sum(b["issued"] for b in bank_totals.values())
	in_bank_received = sum(b["received"] for b in bank_totals.values())
	total_issued = pending_issued + in_bank_issued
	total_received = pending_received + in_bank_received

	def summary_row(label, amount, bank=""):
		return {
			"reference_date": None,
			"reference_no": "",
			"party_type": "",
			"party": "",
			"party_name": label,
			"pdc_status": "",
			"direction": "",
			"amount": amount,
			"bank_gl_account": bank,
		}

	# Pending: bank not yet assigned, so kept as one combined block.
	data.append(summary_row(_("TOTAL PENDING - ISSUED (bank not yet assigned)"), pending_issued))
	data.append(summary_row(_("TOTAL PENDING - RECEIVED (bank not yet assigned)"), pending_received))

	# In Bank: split per real bank GL account, since that's already known.
	for bank in sorted(bank_totals.keys()):
		bucket = bank_totals[bank]
		data.append(summary_row(_("TOTAL IN BANK - ISSUED"), bucket["issued"], bank))
		data.append(summary_row(_("TOTAL IN BANK - RECEIVED"), bucket["received"], bank))
		data.append(summary_row(_("NET BANK IMPACT (In Bank only)"), bucket["received"] - bucket["issued"], bank))

	data.append(summary_row(_("TOTAL PDC ISSUED (not yet cleared, all banks)"), total_issued))
	data.append(summary_row(_("TOTAL PDC RECEIVED (not yet cleared, all banks)"), total_received))
	data.append(summary_row(_("NET BANK IMPACT (Received - Issued, all banks)"), total_received - total_issued))

	return data
