# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

"""Cheque Allocation Forecast - a forward-looking cash position report.

For each payment "window" (a cut-off day like the 5th/15th/28th) this shows
expected inflows (pending received PDCs + recurring income) and outflows
(pending issued PDCs + recurring expenses), carrying a running "Fund in
Bank" balance from window to window. Negative balance = shortfall.

Sources, reused rather than reinvented:
- PDC Register's exact Payment Entry query and pdc_status derivation
  (Pending = no Clearing Voucher; In Bank = Clearing Voucher without
  clearance_date; Cleared = Clearing Voucher with clearance_date).
  "Pending" here = Pending + In Bank - a Cleared cheque already sits in the
  real bank GL balance, counting it again would double-count.
- Recurring Cash Commitment (Direction In -> Receivable, Out -> Payable),
  expanded from its Start Date/Frequency/End Date exactly like Cash
  Forecast does - it has no dated rows of its own, only a rule.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, add_years, flt, formatdate, get_first_day, get_last_day, getdate

RECURRING_FREQUENCY_STEP = {
	"Weekly": lambda d: add_days(d, 7),
	"Monthly": lambda d: add_months(d, 1),
	"Quarterly": lambda d: add_months(d, 3),
	"Annually": lambda d: add_years(d, 1),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	cutoff_days = get_cutoff_days(filters)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	opening, notes = get_opening_balance(filters)

	rows = get_pending_pdc_rows(filters, cutoff_days) + get_recurring_rows(filters, cutoff_days)
	data = build_data(rows, opening, currency)
	message = get_message(cutoff_days, notes)

	return get_columns(), data, message


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are mandatory"))
	filters.from_date = getdate(filters.from_date)
	filters.to_date = getdate(filters.to_date)
	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date cannot be after To Date"))


def get_cutoff_days(filters):
	raw = filters.get("cutoff_days") or "5,15,28"
	days = sorted({int(part.strip()) for part in raw.split(",") if part.strip()})
	return days or [5, 15, 28]


def get_window_date(date, cutoff_days):
	"""Every transaction falls into the next cut-off day on/after its own
	day-of-month; if none remain in that month, it falls into the last
	(highest) cut-off of that month instead of spilling into next month -
	"last cut-off of month covers up to month end"."""
	day = date.day
	last_day = get_last_day(date).day
	chosen_day = next((d for d in cutoff_days if d >= day), cutoff_days[-1])
	chosen_day = min(chosen_day, last_day)
	return add_days(get_first_day(date), chosen_day - 1)


def get_pdc_modes():
	return frappe.get_all("Mode of Payment", filters={"custom_is_pdc_payment": 1}, pluck="name")


def get_pending_pdc_rows(filters, cutoff_days):
	pdc_modes = get_pdc_modes()
	if not pdc_modes:
		return []

	pe_rows = frappe.get_all(
		"Payment Entry",
		filters={
			"company": filters.company,
			"docstatus": ["!=", 2],
			"mode_of_payment": ["in", pdc_modes],
			"payment_type": ["in", ["Receive", "Pay"]],
			"reference_date": ["between", [filters.from_date, filters.to_date]],
		},
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
			"custom_clearing_voucher_type",
			"custom_clearing_voucher_no",
		],
		order_by="reference_date asc",
	)
	if not pe_rows:
		return []

	vouchers_by_type = {}
	for r in pe_rows:
		if r.custom_clearing_voucher_type and r.custom_clearing_voucher_no:
			vouchers_by_type.setdefault(r.custom_clearing_voucher_type, set()).add(r.custom_clearing_voucher_no)

	clearance_by_voucher = {}
	for vtype, names in vouchers_by_type.items():
		for t in frappe.get_all(vtype, filters={"name": ["in", list(names)]}, fields=["name", "clearance_date"]):
			clearance_by_voucher[(vtype, t.name)] = t.clearance_date

	result = []
	for r in pe_rows:
		voucher_key = (r.custom_clearing_voucher_type, r.custom_clearing_voucher_no)
		if not r.custom_clearing_voucher_no:
			pdc_status = "Pending"
		elif clearance_by_voucher.get(voucher_key):
			pdc_status = "Cleared"
		else:
			pdc_status = "In Bank"

		if pdc_status == "Cleared" or not r.reference_no:
			continue

		is_receive = r.payment_type == "Receive"
		cheque_date = getdate(r.reference_date)
		result.append(
			{
				"direction": "In" if is_receive else "Out",
				"party_name": r.party_name or r.party or "",
				"cheque_no": r.reference_no,
				"cheque_date": cheque_date,
				"amount": flt(r.received_amount if is_receive else r.paid_amount),
				"window_date": get_window_date(cheque_date, cutoff_days),
				"reference": f"Payment Entry: {r.name}",
			}
		)

	return result


def get_recurring_rows(filters, cutoff_days):
	commitments = frappe.get_all(
		"Recurring Cash Commitment",
		filters={"company": filters.company, "is_active": 1},
		fields=["name", "title", "direction", "amount", "frequency", "start_date", "end_date"],
	)
	if not commitments:
		return []

	result = []
	for c in commitments:
		for occurrence_date in generate_occurrences(
			getdate(c.start_date),
			getdate(c.end_date) if c.end_date else None,
			c.frequency,
			filters.from_date,
			filters.to_date,
		):
			result.append(
				{
					"direction": c.direction,
					"party_name": c.title,
					"cheque_no": "",
					"cheque_date": occurrence_date,
					"amount": flt(c.amount),
					"window_date": get_window_date(occurrence_date, cutoff_days),
					"reference": f"Recurring Cash Commitment: {c.name}",
				}
			)

	return result


def generate_occurrences(start_date, end_date, frequency, window_start, window_end):
	if frequency == "One-Time":
		return [start_date] if window_start <= start_date <= window_end else []

	step = RECURRING_FREQUENCY_STEP.get(frequency)
	if not step:
		return []

	occurrences = []
	current = start_date
	while current <= window_end and (not end_date or current <= end_date):
		if current >= window_start:
			occurrences.append(current)
		current = step(current)

	return occurrences


def get_cheques_in_hand_accounts():
	"""Accounts a PDC-flagged Mode of Payment posts to before a cheque
	reaches a real bank (al_buraq.setup.setup_pdc_config creates these with
	account_type=Bank too) - excluded from the sweep below, or a Pending/In
	Bank cheque's holding balance would double-count against the real bank
	balance."""
	pdc_modes = get_pdc_modes()
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


def get_opening_balance(filters):
	if filters.get("opening_balance_override") not in (None, ""):
		return flt(filters.opening_balance_override), []

	notes = []
	if filters.get("bank_account"):
		accounts = [filters.bank_account]
	else:
		exclude = get_cheques_in_hand_accounts()
		accounts = [
			a
			for a in frappe.get_all(
				"Account",
				filters={"company": filters.company, "account_type": "Bank", "is_group": 0, "disabled": 0},
				pluck="name",
			)
			if a not in exclude
		]

	if not accounts:
		notes.append(
			_(
				"No Bank account (Chart of Accounts, type Bank) found for this Company - Opening Fund in Bank taken as 0. Add one, pick it via the Bank Account filter, or use Opening Balance Override."
			)
		)
		return 0.0, notes

	opening_date = add_days(filters.from_date, -1)
	result = frappe.db.sql(
		"""select sum(debit) - sum(credit) as balance from `tabGL Entry`
		where account in %(accounts)s and company = %(company)s
			and posting_date <= %(opening_date)s and is_cancelled = 0 and docstatus = 1""",
		{"accounts": tuple(accounts), "company": filters.company, "opening_date": opening_date},
		as_dict=True,
	)
	return flt(result[0].balance) if result else 0.0, notes


def build_data(rows, opening, currency):
	window_dates = sorted({r["window_date"] for r in rows})

	data = []
	opening_running = opening
	grand_recv = grand_pay = 0.0
	month_recv = month_pay = 0.0
	current_month_label = None

	for window_date in window_dates:
		window_rows = [r for r in rows if r["window_date"] == window_date]
		recv_list = sorted(
			(r for r in window_rows if r["direction"] == "In"), key=lambda r: (r["cheque_date"], r["party_name"])
		)
		pay_list = sorted(
			(r for r in window_rows if r["direction"] == "Out"), key=lambda r: (r["cheque_date"], r["party_name"])
		)

		month_label = formatdate(window_date, "MMMM yyyy")
		if current_month_label is None:
			current_month_label = month_label
		if month_label != current_month_label:
			data += month_total_rows(current_month_label, month_recv, month_pay, currency)
			month_recv = month_pay = 0.0
			current_month_label = month_label

		data.append(
			{
				"recv_party": _("Opening Fund in Bank"),
				"recv_amount": opening_running,
				"is_total": 1,
				"row_type": "opening_fund",
				"currency": currency,
			}
		)

		for i in range(max(len(recv_list), len(pay_list))):
			detail_row = {"row_type": "detail", "currency": currency}
			if i < len(recv_list):
				r = recv_list[i]
				detail_row.update(
					recv_party=r["party_name"],
					recv_chq_no=r["cheque_no"],
					recv_chq_date=r["cheque_date"],
					recv_amount=r["amount"],
					recv_reference=r["reference"],
				)
			if i < len(pay_list):
				p = pay_list[i]
				detail_row.update(
					pay_party=p["party_name"],
					pay_chq_no=p["cheque_no"],
					pay_chq_date=p["cheque_date"],
					pay_amount=p["amount"],
					pay_reference=p["reference"],
				)
			data.append(detail_row)

		recv_total = sum(flt(r["amount"]) for r in recv_list)
		pay_total = sum(flt(p["amount"]) for p in pay_list)
		window_label = formatdate(window_date, "dd-MMM-yyyy")

		data.append(
			{
				"recv_party": _("Window Total") + f" - {window_label}",
				"recv_amount": opening_running + recv_total,
				"pay_party": _("Window Total") + f" - {window_label}",
				"pay_amount": pay_total,
				"is_total": 1,
				"row_type": "window_total",
				"currency": currency,
			}
		)

		closing = (opening_running + recv_total) - pay_total
		data.append(
			{
				"recv_party": _("Fund in Bank as on") + f" {window_label}",
				"recv_amount": closing,
				"is_total": 1,
				"row_type": "fund",
				"currency": currency,
			}
		)

		opening_running = closing
		month_recv += recv_total
		month_pay += pay_total
		grand_recv += recv_total
		grand_pay += pay_total

	if current_month_label is not None:
		data += month_total_rows(current_month_label, month_recv, month_pay, currency)

	data.append(
		{
			"recv_party": _("Grand Total Receivable"),
			"recv_amount": grand_recv,
			"pay_party": _("Grand Total Payable"),
			"pay_amount": grand_pay,
			"is_total": 1,
			"row_type": "grand_total",
			"currency": currency,
		}
	)
	data.append(
		{
			"recv_party": _("Closing Fund in Bank"),
			"recv_amount": opening_running,
			"is_total": 1,
			"row_type": "closing_fund",
			"currency": currency,
		}
	)

	return data


def month_total_rows(month_label, month_recv, month_pay, currency):
	return [
		{
			"recv_party": f"{month_label} " + _("Total Receivable"),
			"recv_amount": month_recv,
			"is_total": 1,
			"row_type": "month_total",
			"currency": currency,
		},
		{
			"pay_party": f"{month_label} " + _("Total Payable"),
			"pay_amount": month_pay,
			"is_total": 1,
			"row_type": "month_total",
			"currency": currency,
		},
	]


def get_columns():
	return [
		{"label": _("Recv Party / Description"), "fieldname": "recv_party", "fieldtype": "Data", "width": 190},
		{"label": _("Recv Chq No"), "fieldname": "recv_chq_no", "fieldtype": "Data", "width": 100},
		{"label": _("Recv Chq Date"), "fieldname": "recv_chq_date", "fieldtype": "Date", "width": 100},
		{"label": _("Recv Amount"), "fieldname": "recv_amount", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Pay Party / Description"), "fieldname": "pay_party", "fieldtype": "Data", "width": 190},
		{"label": _("Pay Chq No"), "fieldname": "pay_chq_no", "fieldtype": "Data", "width": 100},
		{"label": _("Pay Chq Date"), "fieldname": "pay_chq_date", "fieldtype": "Date", "width": 100},
		{"label": _("Pay Amount"), "fieldname": "pay_amount", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Recv Reference"), "fieldname": "recv_reference", "fieldtype": "Data", "width": 200, "hidden": 1},
		{"label": _("Pay Reference"), "fieldname": "pay_reference", "fieldtype": "Data", "width": 200, "hidden": 1},
		{"label": _("Row Type"), "fieldname": "row_type", "fieldtype": "Data", "width": 100, "hidden": 1},
		{"label": _("Is Total"), "fieldname": "is_total", "fieldtype": "Check", "width": 80, "hidden": 1},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 80, "hidden": 1},
	]


def get_message(cutoff_days, notes):
	parts = [
		_("Pending PDC = PDC Register's own Pending/In Bank cheques (Cleared cheques already reflected in the real bank balance are excluded)."),
		_("Recurring expense/income occurrences are projected from Recurring Cash Commitment's Start Date/Frequency/End Date, the same way Cash Forecast does."),
		_("Window cut-off days: {0}. A transaction falls into the next cut-off on/after its date; the last cut-off of a month covers everything up to month end.").format(
			", ".join(str(d) for d in cutoff_days)
		),
	]
	parts += notes
	return "<br>".join(parts)
