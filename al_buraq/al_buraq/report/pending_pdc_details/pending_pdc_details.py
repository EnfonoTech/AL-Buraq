# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

"""Pending PDC Details - every cash item still outstanding and not yet in
the bank: Pending post-dated cheques (Payment Entry against a PDC-flagged
Mode of Payment, with no Clearing Voucher yet at all - "In Bank"/"Cleared"
cheques are deliberately excluded, they belong in PDC Register/PDC Bank
Projection/PDC Allocation instead) alongside upcoming expense occurrences
from Recurring Cash Commitment (Direction=Out - payroll, rent, loan EMI,
VAT/ZATCA settlements, etc.), projected the same way Cash Forecast does.
One unified, date-sorted list tagged by Source.
"""

import frappe
from dateutil.relativedelta import relativedelta
from frappe import _
from frappe.utils import flt, getdate

PDC = "PDC"
RECURRING = "Recurring Commitment"

RECURRING_FREQUENCY_STEP = {
	"Weekly": relativedelta(weeks=1),
	"Monthly": relativedelta(months=1),
	"Quarterly": relativedelta(months=3),
	"Annually": relativedelta(years=1),
}


def get_pdc_modes():
	return frappe.get_all("Mode of Payment", filters={"custom_is_pdc_payment": 1}, pluck="name")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	rows = []
	if filters.get("source") != RECURRING:
		rows += get_pending_pdc_rows(filters)
	if filters.get("source") != PDC:
		rows += get_recurring_commitment_rows(filters)

	rows.sort(key=lambda r: (r["due_date"], r["source"], r["party_name"] or ""))

	return get_columns(), rows, None, get_chart(rows), get_summary(rows)


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are mandatory"))
	filters.from_date = getdate(filters.from_date)
	filters.to_date = getdate(filters.to_date)
	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date cannot be after To Date"))


# ---------------------------------------------------------------- PDC
def get_pending_pdc_rows(filters):
	pdc_modes = get_pdc_modes()
	if not pdc_modes:
		return []

	# Cheque date (reference_date) is what bounds this report, not any Payment
	# Entry lifecycle field (posting_date, docstatus history, etc.) - with
	# Include Overdue off, a cheque outside [From Date, To Date] never shows
	# up regardless of when its Payment Entry was posted.
	if filters.get("include_overdue"):
		reference_date_filter = ["<=", filters.to_date]
	else:
		reference_date_filter = ["between", [filters.from_date, filters.to_date]]

	conditions = {
		"company": filters.company,
		"docstatus": 1,
		"mode_of_payment": ["in", pdc_modes],
		"payment_type": ["in", ["Receive", "Pay"]],
		"reference_date": reference_date_filter,
		"custom_clearing_voucher_no": ["in", ["", None]],
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
		],
		order_by="reference_date asc",
	)

	result = []
	for r in rows:
		if not r.reference_no:
			continue
		due_date = getdate(r.reference_date)

		is_receive = r.payment_type == "Receive"
		direction = "In" if is_receive else "Out"
		if filters.get("direction") and direction != filters.direction:
			continue
		if filters.get("party_type") and r.party_type != filters.party_type:
			continue
		if filters.get("party") and r.party != filters.party:
			continue

		result.append(
			{
				"source": PDC,
				"due_date": due_date,
				"direction": direction,
				"party_type": r.party_type,
				"party": r.party,
				"party_name": r.party_name or r.party,
				"cheque_no": r.reference_no,
				"amount": flt(r.received_amount) if is_receive else flt(r.paid_amount),
				"confidence": "Confirmed",
				"classification": "",
				"cost_center": "",
				"voucher_type": "Payment Entry",
				"voucher_no": r.name,
				"remarks": _("Overdue") if due_date < filters.from_date else "",
			}
		)

	return result


# ---------------------------------------------------------------- Recurring Cash Commitment
def get_recurring_commitment_rows(filters):
	"""Expense occurrences (Direction=Out) from Recurring Cash Commitment,
	projected forward from (Start Date, Frequency, End Date) exactly like
	Cash Forecast - nothing is stored, so there is nothing to keep in sync
	as the date range changes."""
	conditions = {"company": filters.company, "is_active": 1, "direction": "Out"}
	if filters.get("direction") and filters.direction != "Out":
		return []

	commitments = frappe.get_all(
		"Recurring Cash Commitment",
		filters=conditions,
		fields=[
			"name",
			"title",
			"amount",
			"frequency",
			"start_date",
			"end_date",
			"cost_center",
			"confidence",
			"classification",
		],
	)
	if not commitments:
		return []

	result = []
	for c in commitments:
		occurrences = _generate_occurrences(
			getdate(c.start_date),
			getdate(c.end_date) if c.end_date else None,
			c.frequency,
			filters.from_date,
			filters.to_date,
		)
		for occurrence_date in occurrences:
			result.append(
				{
					"source": RECURRING,
					"due_date": occurrence_date,
					"direction": "Out",
					"party_type": "",
					"party": "",
					"party_name": c.title,
					"cheque_no": "",
					"amount": flt(c.amount),
					"confidence": c.confidence,
					"classification": c.classification,
					"cost_center": c.cost_center,
					"voucher_type": "Recurring Cash Commitment",
					"voucher_no": c.name,
					"remarks": "",
				}
			)

	return result


def _generate_occurrences(start_date, end_date, frequency, window_start, window_end):
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
		current = current + step

	return occurrences


# ---------------------------------------------------------------- output
def get_columns():
	return [
		{"label": _("Source"), "fieldname": "source", "fieldtype": "Data", "width": 130},
		{"label": _("Due Date"), "fieldname": "due_date", "fieldtype": "Date", "width": 100},
		{"label": _("Direction"), "fieldname": "direction", "fieldtype": "Data", "width": 80},
		{"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data", "width": 90},
		{"label": _("Party"), "fieldname": "party", "fieldtype": "Dynamic Link", "options": "party_type", "width": 130},
		{"label": _("Party / Title"), "fieldname": "party_name", "fieldtype": "Data", "width": 200},
		{"label": _("Cheque No"), "fieldname": "cheque_no", "fieldtype": "Data", "width": 100},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Confidence"), "fieldname": "confidence", "fieldtype": "Data", "width": 100},
		{"label": _("Classification"), "fieldname": "classification", "fieldtype": "Data", "width": 140},
		{"label": _("Cost Center"), "fieldname": "cost_center", "fieldtype": "Link", "options": "Cost Center", "width": 140},
		{"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 150},
		{"label": _("Voucher No"), "fieldname": "voucher_no", "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 160},
		{"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 100},
	]


def get_chart(rows):
	if not rows:
		return None

	by_source = {}
	for r in rows:
		bucket = by_source.setdefault(r["source"], {"In": 0.0, "Out": 0.0})
		bucket[r["direction"]] += flt(r["amount"])

	labels = list(by_source)
	return {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("In"), "values": [by_source[s]["In"] for s in labels]},
				{"name": _("Out"), "values": [by_source[s]["Out"] for s in labels]},
			],
		},
		"type": "bar",
	}


def get_summary(rows):
	total_in = sum(flt(r["amount"]) for r in rows if r["direction"] == "In")
	total_out = sum(flt(r["amount"]) for r in rows if r["direction"] == "Out")
	pdc_count = sum(1 for r in rows if r["source"] == PDC)
	recurring_count = sum(1 for r in rows if r["source"] == RECURRING)

	return [
		{"value": pdc_count, "label": _("Pending PDCs"), "datatype": "Int", "indicator": "Blue"},
		{"value": recurring_count, "label": _("Recurring Commitment Occurrences"), "datatype": "Int", "indicator": "Blue"},
		{"value": total_in, "label": _("Total In"), "datatype": "Currency", "indicator": "Green"},
		{"value": total_out, "label": _("Total Out"), "datatype": "Currency", "indicator": "Red"},
		{"value": total_in - total_out, "label": _("Net"), "datatype": "Currency", "indicator": "Green" if total_in >= total_out else "Red"},
	]
