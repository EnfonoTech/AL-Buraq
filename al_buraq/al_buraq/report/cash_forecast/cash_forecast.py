# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from dateutil.relativedelta import relativedelta
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Sum
from frappe.utils import add_days, flt, getdate

from al_buraq.al_buraq.doctype.budget_scenario.budget_scenario import SPECIFICITY

RECONCILE_TOLERANCE = 0.01

INVOICE_EXCLUDED_STATUS = {
	"Sales Invoice": ["Paid", "Cancelled", "Credit Note Issued", "Internal Transfer", "Draft"],
	"Purchase Invoice": ["Paid", "Cancelled", "Debit Note Issued", "Internal Transfer", "Draft"],
}

ORDER_PARTY_FIELD = {"Sales Order": "customer", "Purchase Order": "supplier"}
ORDER_ITEM_DATE_FIELD = {"Sales Order": "delivery_date", "Purchase Order": "schedule_date"}
ORDER_EXCLUDED_STATUS = ["Closed", "On Hold"]

# Trade rows (invoices/orders) are always Operating cash flow — Investing/
# Financing/VAT-ZATCA only ever come from an explicit Recurring Cash
# Commitment, where Finance tags it directly (see that doctype).
TRADE_CLASSIFICATION = "Operating"

RECURRING_FREQUENCY_STEP = {
	"Weekly": relativedelta(weeks=1),
	"Monthly": relativedelta(months=1),
	"Quarterly": relativedelta(months=3),
	"Annually": relativedelta(years=1),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	rows, warnings = get_cash_flow_rows(filters)
	buckets = build_buckets(filters, rows)

	if filters.get("show_details"):
		columns = get_detail_columns()
		data = sorted(rows, key=lambda r: r["due_date"] or getdate())
	else:
		columns = get_summary_columns()
		data = buckets

	message = get_message(filters, warnings)
	chart = get_chart_data(buckets) if not filters.get("show_details") else None
	return columns, data, message, chart


def get_chart_data(buckets):
	if not buckets:
		return None
	return {
		"data": {
			"labels": [b["period"] for b in buckets],
			"datasets": [
				{"name": _("Inflow"), "values": [b["inflow"] for b in buckets], "chartType": "bar"},
				{"name": _("Outflow"), "values": [b["outflow"] for b in buckets], "chartType": "bar"},
				{"name": _("Closing Position"), "values": [b["cumulative_cash"] for b in buckets], "chartType": "line"},
			],
		},
		"type": "axis-mixed",
		"barOptions": {"stacked": 1},
	}


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))
	filters.setdefault("from_date", frappe.utils.nowdate())
	filters.setdefault("to_date", add_days(filters.from_date, 90))
	filters.setdefault("bucket", "Monthly")
	filters.setdefault("include_overdue", 1)
	filters.setdefault("include_opening_cash", 1)
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date"))


def get_summary_columns():
	return [
		{"label": _("Period"), "fieldname": "period", "fieldtype": "Data", "width": 140},
		{"label": _("Period Start"), "fieldname": "period_start", "fieldtype": "Date", "width": 1, "hidden": 1},
		{"label": _("Period End"), "fieldname": "period_end", "fieldtype": "Date", "width": 1, "hidden": 1},
		{"label": _("Inflow"), "fieldname": "inflow", "fieldtype": "Currency", "width": 130},
		{"label": _("Outflow"), "fieldname": "outflow", "fieldtype": "Currency", "width": 130},
		{"label": _("Net Movement"), "fieldname": "net_movement", "fieldtype": "Currency", "width": 130},
		{"label": _("Cumulative Cash"), "fieldname": "cumulative_cash", "fieldtype": "Currency", "width": 140},
		{"label": _("VAT/ZATCA Net"), "fieldname": "vat_zatca_net", "fieldtype": "Currency", "width": 130},
		{"label": _("Invoice Count"), "fieldname": "invoice_count", "fieldtype": "Int", "width": 100},
	]


def get_detail_columns():
	return [
		{"label": _("Due Date"), "fieldname": "due_date", "fieldtype": "Date", "width": 100},
		{"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 120},
		{
			"label": _("Voucher No"),
			"fieldname": "voucher_no",
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 140,
		},
		{"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data", "width": 90},
		{"label": _("Party"), "fieldname": "party", "fieldtype": "Dynamic Link", "options": "party_type", "width": 160},
		{"label": _("Direction"), "fieldname": "direction", "fieldtype": "Data", "width": 70},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 130},
		{"label": _("Days Overdue"), "fieldname": "days_overdue", "fieldtype": "Int", "width": 90},
		{"label": _("Confidence"), "fieldname": "confidence", "fieldtype": "Data", "width": 100},
		{"label": _("Classification"), "fieldname": "classification", "fieldtype": "Data", "width": 130},
	]


def get_cash_flow_rows(filters):
	warnings = []

	si_schedule, si_currency_warnings = _get_schedule_rows(filters, "Sales Invoice")
	pi_schedule, pi_currency_warnings = _get_schedule_rows(filters, "Purchase Invoice")
	si_fallback, si_fallback_warnings = _get_fallback_rows(filters, "Sales Invoice")
	pi_fallback, pi_fallback_warnings = _get_fallback_rows(filters, "Purchase Invoice")

	warnings += si_currency_warnings + pi_currency_warnings + si_fallback_warnings + pi_fallback_warnings

	rows = si_schedule + pi_schedule + si_fallback + pi_fallback

	if filters.get("include_sales_orders", 1):
		rows += _get_order_rows(filters, "Sales Order")
	if filters.get("include_purchase_orders", 1):
		rows += _get_order_rows(filters, "Purchase Order")

	if filters.get("include_recurring", 1):
		rows += _get_recurring_rows(filters)

	if filters.get("apply_scenario"):
		rows = _apply_scenario_delay(rows, filters)

	today = getdate()
	for row in rows:
		if not row.get("direction"):
			row["direction"] = "In" if row["party_type"] == "Customer" else "Out"
		row["days_overdue"] = max(0, (today - row["due_date"]).days) if row["due_date"] else 0

	if filters.get("cost_center"):
		rows = [r for r in rows if r.get("cost_center") == filters.cost_center]

	if filters.get("classification"):
		rows = [r for r in rows if r.get("classification") == filters.classification]

	return rows, warnings


def _get_schedule_rows(filters, doctype):
	"""Payment Schedule rows for invoices that use Payment Terms, scaled
	to the invoice's authoritative outstanding_amount when Payment Entry
	hasn't kept base_outstanding in sync (e.g. settlement via Journal
	Entry, which never touches Payment Schedule)."""
	ps = frappe.qb.DocType("Payment Schedule")
	inv = frappe.qb.DocType(doctype)
	party_field = "customer" if doctype == "Sales Invoice" else "supplier"
	party_type = "Customer" if doctype == "Sales Invoice" else "Supplier"

	query = (
		frappe.qb.from_(ps)
		.inner_join(inv)
		.on((ps.parent == inv.name) & (ps.parenttype == doctype))
		.select(
			inv.name.as_("voucher_no"),
			inv[party_field].as_("party"),
			inv.cost_center,
			inv.outstanding_amount,
			inv.conversion_rate,
			inv.currency,
			inv.party_account_currency,
			ps.due_date,
			ps.base_outstanding,
		)
		.where(inv.docstatus == 1)
		.where(inv.company == filters.company)
		.where(inv.is_return == 0)
		.where(inv.status.notin(INVOICE_EXCLUDED_STATUS[doctype]))
		.where(inv.outstanding_amount > 0)
		.where(ps.base_outstanding > 0)
		.where(ps.due_date <= filters.to_date)
	)
	if filters.get("party_type") and filters.party_type != party_type:
		return [], []

	schedule_rows = query.run(as_dict=True)

	by_voucher = {}
	for row in schedule_rows:
		by_voucher.setdefault(row.voucher_no, []).append(row)

	rows = []
	warnings = []
	for voucher_no, legs in by_voucher.items():
		first = legs[0]
		authoritative = flt(first.outstanding_amount) * flt(first.conversion_rate or 1)
		schedule_total = sum(flt(leg.base_outstanding) for leg in legs)

		scale = 1.0
		if schedule_total and abs(schedule_total - authoritative) > RECONCILE_TOLERANCE:
			scale = authoritative / schedule_total
			warnings.append(
				_("{0} {1}: Payment Schedule total ({2}) did not match outstanding amount ({3}) — likely settled partly via Journal Entry. Schedule rows scaled proportionally.").format(
					doctype, voucher_no, schedule_total, authoritative
				)
			)

		for leg in legs:
			rows.append(
				{
					"voucher_type": doctype,
					"voucher_no": voucher_no,
					"party_type": party_type,
					"party": leg.party,
					"cost_center": leg.cost_center,
					"due_date": getdate(leg.due_date) if leg.due_date else None,
					"amount": flt(leg.base_outstanding) * scale,
					"confidence": "Confirmed",
					"classification": TRADE_CLASSIFICATION,
				}
			)

	return rows, warnings


def _get_fallback_rows(filters, doctype):
	"""Invoices with no Payment Schedule rows at all (most invoices,
	unless Payment Terms are used) — without this branch the forecast
	silently under-reports."""
	inv = frappe.qb.DocType(doctype)
	ps = frappe.qb.DocType("Payment Schedule")
	party_field = "customer" if doctype == "Sales Invoice" else "supplier"
	party_type = "Customer" if doctype == "Sales Invoice" else "Supplier"

	if filters.get("party_type") and filters.party_type != party_type:
		return [], []

	has_schedule = frappe.qb.from_(ps).select(ps.parent).where(ps.parenttype == doctype)

	due_date = Case().when(inv.due_date.isnull(), inv.posting_date).else_(inv.due_date)

	query = (
		frappe.qb.from_(inv)
		.select(
			inv.name.as_("voucher_no"),
			inv[party_field].as_("party"),
			inv.cost_center,
			inv.outstanding_amount,
			inv.conversion_rate,
			inv.currency,
			inv.party_account_currency,
			due_date.as_("due_date"),
		)
		.where(inv.docstatus == 1)
		.where(inv.company == filters.company)
		.where(inv.is_return == 0)
		.where(inv.status.notin(INVOICE_EXCLUDED_STATUS[doctype]))
		.where(inv.outstanding_amount > 0)
		.where(due_date <= filters.to_date)
		.where(inv.name.notin(has_schedule))
	)

	rows = query.run(as_dict=True)

	result = []
	warnings = []
	for row in rows:
		if row.party_account_currency and row.currency and row.party_account_currency != row.currency:
			warnings.append(
				_("{0} {1}: outstanding amount is held in {2}, different from the invoice currency {3} — excluded from the forecast to avoid reporting a wrong amount.").format(
					doctype, row.voucher_no, row.party_account_currency, row.currency
				)
			)
			continue

		result.append(
			{
				"voucher_type": doctype,
				"voucher_no": row.voucher_no,
				"party_type": party_type,
				"party": row.party,
				"cost_center": row.cost_center,
				"due_date": getdate(row.due_date) if row.due_date else None,
				"amount": flt(row.outstanding_amount) * flt(row.conversion_rate or 1),
				"confidence": "Confirmed",
				"classification": TRADE_CLASSIFICATION,
			}
		)

	return result, warnings


def _get_order_rows(filters, doctype):
	"""Unbilled Sales/Purchase Order amounts — the pipeline that hasn't
	reached an invoice yet. Uses (item.amount - item.billed_amt), so an
	order's rows shrink to zero as it gets invoiced and the corresponding
	invoice rows take over — no double-counting between the two.

	Timing prefers the order's own Payment Schedule (advance/installment
	terms) when present, scaled down to the still-unbilled fraction of the
	order since the schedule itself isn't reduced by invoicing. Orders with
	no Payment Schedule fall back to item Delivery/Schedule Date.
	"""
	item_dt = f"{doctype} Item"
	party_field = ORDER_PARTY_FIELD[doctype]
	party_type = "Customer" if doctype == "Sales Order" else "Supplier"
	date_field_name = ORDER_ITEM_DATE_FIELD[doctype]

	oi = frappe.qb.DocType(item_dt)
	o = frappe.qb.DocType(doctype)
	unbilled_amount = (oi.amount - oi.billed_amt) * o.conversion_rate
	item_date = Case().when(oi[date_field_name].isnull(), o.transaction_date).else_(oi[date_field_name])

	query = (
		frappe.qb.from_(oi)
		.inner_join(o)
		.on(oi.parent == o.name)
		.select(
			o.name.as_("voucher_no"),
			o[party_field].as_("party"),
			oi.cost_center,
			o.base_grand_total,
			unbilled_amount.as_("amount"),
			item_date.as_("due_date"),
		)
		.where(o.docstatus == 1)
		.where(o.company == filters.company)
		.where(o.status.notin(ORDER_EXCLUDED_STATUS))
		.where(oi.amount > oi.billed_amt)
	)
	if filters.get("party_type") and filters.party_type != party_type:
		return []

	item_rows = query.run(as_dict=True)
	if not item_rows:
		return []

	unbilled_by_order = {}
	for row in item_rows:
		unbilled_by_order[row.voucher_no] = flt(unbilled_by_order.get(row.voucher_no, 0)) + flt(row.amount)

	schedule_by_order = _get_order_schedule_rows(doctype, list(unbilled_by_order))

	rows = []
	for voucher_no, order_rows in _group_by(item_rows, "voucher_no").items():
		schedule_rows = schedule_by_order.get(voucher_no)
		unbilled_total = unbilled_by_order[voucher_no]

		if schedule_rows and flt(order_rows[0].base_grand_total):
			fraction = unbilled_total / flt(order_rows[0].base_grand_total)
			fallback_cost_center = order_rows[0].cost_center
			for sched in schedule_rows:
				rows.append(
					{
						"voucher_type": doctype,
						"voucher_no": voucher_no,
						"party_type": party_type,
						"party": order_rows[0].party,
						"cost_center": fallback_cost_center,
						"due_date": getdate(sched.due_date) if sched.due_date else None,
						"amount": flt(sched.base_outstanding) * fraction,
						"confidence": "Probable",
						"classification": TRADE_CLASSIFICATION,
					}
				)
		else:
			for item_row in order_rows:
				if not item_row.due_date:
					continue
				rows.append(
					{
						"voucher_type": doctype,
						"voucher_no": voucher_no,
						"party_type": party_type,
						"party": item_row.party,
						"cost_center": item_row.cost_center,
						"due_date": getdate(item_row.due_date),
						"amount": flt(item_row.amount),
						"confidence": "Probable",
						"classification": TRADE_CLASSIFICATION,
					}
				)

	return [r for r in rows if r["due_date"] and r["due_date"] <= getdate(filters.to_date)]


def _get_order_schedule_rows(doctype, voucher_names):
	"""One query. {voucher_no: [Payment Schedule row, ...]} for the given
	Sales/Purchase Order names, oldest due date first."""
	if not voucher_names:
		return {}

	ps = frappe.qb.DocType("Payment Schedule")
	rows = (
		frappe.qb.from_(ps)
		.select(ps.parent, ps.due_date, ps.base_outstanding)
		.where(ps.parenttype == doctype)
		.where(ps.parent.isin(voucher_names))
		.where(ps.base_outstanding > 0)
		.orderby(ps.due_date)
		.run(as_dict=True)
	)
	return _group_by(rows, "parent")


def _group_by(rows, key):
	grouped = {}
	for row in rows:
		grouped.setdefault(row[key], []).append(row)
	return grouped


def _get_recurring_rows(filters):
	"""Payroll, rent, loan EMI and other fixed commitments Finance
	maintains directly (Recurring Cash Commitment) — never an ERPNext
	transaction, so unlike every other row here this is a projection, not
	a tracked outstanding amount. Occurrences are generated fresh from
	(Start Date, Frequency, End Date) rather than stored, so there is
	nothing to keep in sync as the report's date range changes.
	"""
	commitments = frappe.get_all(
		"Recurring Cash Commitment",
		filters={"company": filters.company, "is_active": 1},
		fields=["name", "title", "direction", "amount", "frequency", "start_date", "end_date", "cost_center", "confidence", "classification"],
	)
	if not commitments:
		return []

	window_start = getdate(filters.from_date)
	window_end = getdate(filters.to_date)

	rows = []
	for commitment in commitments:
		occurrences = _generate_occurrences(
			getdate(commitment.start_date),
			getdate(commitment.end_date) if commitment.end_date else None,
			commitment.frequency,
			window_start,
			window_end,
		)
		for occurrence_date in occurrences:
			rows.append(
				{
					"voucher_type": "Recurring Cash Commitment",
					"voucher_no": commitment.name,
					"party_type": None,
					"party": commitment.title,
					"cost_center": commitment.cost_center,
					"due_date": occurrence_date,
					"amount": flt(commitment.amount),
					"direction": commitment.direction,
					"confidence": commitment.confidence,
					"classification": commitment.classification,
				}
			)

	return rows


def _generate_occurrences(start_date, end_date, frequency, window_start, window_end):
	"""Every occurrence date within [window_start, window_end]. Recurring
	commitments have no tracked outstanding state (unlike invoices/orders),
	so occurrences before window_start are never generated — there is no
	such thing as an 'overdue' recurring commitment here, only future
	scheduled ones.
	"""
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


def _apply_scenario_delay(rows, filters):
	"""What-if overlay: shifts due dates by the 'Delay in Days' lines of
	the selected Budget Scenario — e.g. "customer collections delayed by
	15 days". Calculation-only: this never writes to the Budget Scenario,
	GL Entry, or any transaction — only the in-memory rows for this report
	run are shifted, exactly like every other scenario adjustment in this
	suite.
	"""
	scenario = frappe.db.get_value(
		"Budget Scenario", filters.apply_scenario, ["company", "budget_against"], as_dict=True
	)
	if not scenario:
		frappe.throw(_("Budget Scenario {0} not found").format(filters.apply_scenario))
	if scenario.company != filters.company:
		frappe.throw(_("Budget Scenario {0} belongs to a different Company").format(filters.apply_scenario))
	if scenario.budget_against != "Cost Center":
		frappe.throw(_("Only Cost Center-based Budget Scenarios can be applied to Cash Forecast (rows have no Project)"))

	delay_lines = frappe.get_all(
		"Budget Scenario Line",
		filters={"parent": filters.apply_scenario, "adjustment_type": "Delay in Days"},
		fields=["apply_to", "cost_center", "party_type", "adjustment_value"],
	)
	if not delay_lines:
		return rows

	delay_lines = sorted(delay_lines, key=lambda line: SPECIFICITY.get(line.apply_to, 0))
	to_date = getdate(filters.to_date)

	result = []
	for row in rows:
		if not row["due_date"]:
			result.append(row)
			continue

		for line in delay_lines:
			if line.apply_to == "Cost Center" and line.cost_center != row.get("cost_center"):
				continue
			if line.party_type and line.party_type != row.get("party_type"):
				continue
			row["due_date"] = add_days(row["due_date"], line.adjustment_value)

		if row["due_date"] <= to_date:
			result.append(row)

	return result


def get_opening_cash(filters):
	accounts = frappe.get_all(
		"Account",
		filters={"company": filters.company, "account_type": ["in", ["Bank", "Cash"]], "is_group": 0},
		pluck="name",
	)
	if not accounts:
		return 0.0

	gl = frappe.qb.DocType("GL Entry")
	result = (
		frappe.qb.from_(gl)
		.select((Sum(gl.debit) - Sum(gl.credit)).as_("balance"))
		.where(gl.company == filters.company)
		.where(gl.posting_date < filters.from_date)
		.where(gl.is_cancelled == 0)
		.where(gl.docstatus == 1)
		.where(gl.account.isin(accounts))
		.run(as_dict=True)
	)
	return flt(result[0].balance) if result else 0.0


def build_buckets(filters, rows):
	bucket_defs = _get_bucket_labels(filters)

	buckets = []
	for label, start, end in bucket_defs:
		bucket_rows = [
			r for r in rows if r["due_date"] and (
				(label == _("Overdue") and r["due_date"] < getdate(filters.from_date))
				or (start and end and start <= r["due_date"] <= end)
			)
		]
		inflow = sum(flt(r["amount"]) for r in bucket_rows if r["direction"] == "In")
		outflow = sum(flt(r["amount"]) for r in bucket_rows if r["direction"] == "Out")
		vat_zatca_net = sum(
			flt(r["amount"]) if r["direction"] == "In" else -flt(r["amount"])
			for r in bucket_rows
			if r["classification"] == "VAT/ZATCA Settlement"
		)
		buckets.append(
			{
				"period": label,
				"period_start": start,
				"period_end": end,
				"inflow": inflow,
				"outflow": outflow,
				"net_movement": inflow - outflow,
				"vat_zatca_net": vat_zatca_net,
				"invoice_count": len(bucket_rows),
			}
		)

	cumulative = get_opening_cash(filters) if filters.get("include_opening_cash") else 0.0
	for bucket in buckets:
		cumulative += bucket["net_movement"]
		bucket["cumulative_cash"] = cumulative

	return buckets


def _get_bucket_labels(filters):
	bucket_defs = []
	if filters.get("include_overdue"):
		bucket_defs.append((_("Overdue"), None, None))

	start = getdate(filters.from_date)
	end = getdate(filters.to_date)
	step = {"Weekly": relativedelta(weeks=1), "Monthly": relativedelta(months=1), "Quarterly": relativedelta(months=3)}[
		filters.bucket
	]

	cursor = start
	while cursor <= end:
		bucket_end = cursor + step - relativedelta(days=1)
		if bucket_end > end:
			bucket_end = end
		label = "{0} - {1}".format(cursor.strftime("%d-%b"), bucket_end.strftime("%d-%b-%Y"))
		bucket_defs.append((label, cursor, bucket_end))
		cursor = bucket_end + relativedelta(days=1)

	return bucket_defs


def get_message(filters, warnings):
	parts = [
		_("Cash movement is projected from unpaid Payment Schedule rows where Payment Terms are used, and from invoice Outstanding Amount otherwise."),
	]
	if filters.get("include_sales_orders", 1) or filters.get("include_purchase_orders", 1):
		parts.append(
			_("Unbilled Sales/Purchase Order pipeline is included (net of tax), timed by the order's own Payment Schedule where set, otherwise by item Delivery/Schedule Date. This portion shrinks to zero as each order is invoiced, since the invoice then takes over its cash timing.")
		)
	if filters.get("include_recurring", 1):
		parts.append(
			_("Fixed recurring commitments (payroll, rent, loan EMI, VAT/ZATCA settlements, etc.) maintained under Recurring Cash Commitment are included, projected forward from each commitment's Start Date/Frequency.")
		)
	parts.append(
		_("Confidence: Confirmed = posted invoice/recurring commitment; Probable = unbilled Sales/Purchase Order pipeline. Classification: trade rows are Operating; Investing/Financing/VAT-ZATCA come only from Recurring Cash Commitment.")
	)
	parts.append(
		_("VAT/ZATCA Net (summary mode) is the net cash movement of every row classified VAT/ZATCA Settlement in that period — always shown, independent of the Classification filter, for KSA cash-timing visibility.")
	)
	if filters.get("apply_scenario"):
		parts.append(
			_("What-if overlay active: Budget Scenario {0}'s 'Delay in Days' lines have shifted matching due dates for this run only — nothing is written back to any Scenario, GL Entry or transaction.").format(
				filters.apply_scenario
			)
		)
	if filters.get("include_opening_cash"):
		parts.append(_("Cumulative Cash starts from the Bank/Cash GL balance before the From Date."))
	if warnings:
		parts.append("<b>" + _("Reconciliation notes") + ":</b><br>" + "<br>".join(warnings[:20]))
		if len(warnings) > 20:
			parts.append(_("...and {0} more.").format(len(warnings) - 20))
	return "<br>".join(parts)
