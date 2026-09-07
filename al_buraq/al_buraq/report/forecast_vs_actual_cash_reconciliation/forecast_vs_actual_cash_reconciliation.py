# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

"""
Forecast vs Actual Cash Reconciliation — compares a frozen Cash Forecast
Snapshot's prediction against what the Bank/Cash GL balance actually did
over that same period, once the period has closed.

Only closed periods (Period End on or before As Of Date) are shown —
there is nothing to reconcile against for a period still in progress.
Reuses Cash Forecast's own get_opening_cash so "actual" is computed the
exact same way "predicted" was, just with real dates instead of a
forecast bucket.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, formatdate, getdate, nowdate

from al_buraq.al_buraq.report.cash_forecast.cash_forecast import get_opening_cash


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	columns = get_columns()
	data = get_data(filters)
	message = get_message(filters)

	return columns, data, message


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))
	filters.setdefault("as_of_date", nowdate())
	filters.setdefault("latest_snapshot_only", 1)


def get_columns():
	return [
		{"label": _("Period"), "fieldname": "period_label", "fieldtype": "Data", "width": 160},
		{"label": _("Period Start"), "fieldname": "period_start", "fieldtype": "Date", "width": 100},
		{"label": _("Period End"), "fieldname": "period_end", "fieldtype": "Date", "width": 100},
		{"label": _("Snapshot Date"), "fieldname": "snapshot_date", "fieldtype": "Date", "width": 100},
		{"label": _("Predicted Net Movement"), "fieldname": "predicted_net_movement", "fieldtype": "Currency", "width": 160},
		{"label": _("Actual Net Movement"), "fieldname": "actual_net_movement", "fieldtype": "Currency", "width": 150},
		{"label": _("Predicted Closing Position"), "fieldname": "predicted_closing_position", "fieldtype": "Currency", "width": 170},
		{"label": _("Actual Closing Position"), "fieldname": "actual_closing_position", "fieldtype": "Currency", "width": 160},
		{"label": _("Variance"), "fieldname": "variance", "fieldtype": "Currency", "width": 130},
		{"label": _("Variance %"), "fieldname": "variance_percent", "fieldtype": "Percent", "width": 100},
	]


def get_data(filters):
	snapshot = frappe.qb.DocType("Cash Forecast Snapshot")
	query = (
		frappe.qb.from_(snapshot)
		.select(
			snapshot.name,
			snapshot.snapshot_date,
			snapshot.period_label,
			snapshot.period_start,
			snapshot.period_end,
			snapshot.predicted_inflow,
			snapshot.predicted_outflow,
			snapshot.predicted_net_movement,
			snapshot.predicted_closing_position,
		)
		.where(snapshot.company == filters.company)
		.where(snapshot.period_end <= filters.as_of_date)
		.orderby(snapshot.period_start)
		.orderby(snapshot.snapshot_date, order=frappe.qb.desc)
	)
	rows = query.run(as_dict=True)

	if filters.get("latest_snapshot_only"):
		latest_by_period = {}
		for row in rows:
			key = (row.period_start, row.period_end)
			if key not in latest_by_period:
				latest_by_period[key] = row
		rows = list(latest_by_period.values())

	data = []
	for row in rows:
		actual_opening = get_opening_cash(frappe._dict(company=filters.company, from_date=row.period_start))
		actual_closing = get_opening_cash(frappe._dict(company=filters.company, from_date=add_days(row.period_end, 1)))
		actual_net_movement = actual_closing - actual_opening

		variance = actual_closing - flt(row.predicted_closing_position)
		predicted_net = flt(row.predicted_net_movement)

		data.append(
			{
				"period_label": row.period_label,
				"period_start": row.period_start,
				"period_end": row.period_end,
				"snapshot_date": row.snapshot_date,
				"predicted_net_movement": predicted_net,
				"actual_net_movement": actual_net_movement,
				"predicted_closing_position": row.predicted_closing_position,
				"actual_closing_position": actual_closing,
				"variance": variance,
				"variance_percent": ((actual_net_movement - predicted_net) / predicted_net * 100) if predicted_net else 0,
			}
		)

	data.sort(key=lambda r: r["period_start"] or getdate(), reverse=True)
	return data


def get_message(filters):
	parts = [
		_("Only periods that have already closed (Period End on or before {0}) are shown — there is nothing to reconcile for a period still in progress.").format(
			formatdate(filters.as_of_date)
		),
		_("Actual is the real Bank/Cash GL balance at Period Start and Period End — the same calculation Cash Forecast itself uses for Opening Position, just applied retroactively."),
		_("Take a snapshot from the Cash Forecast report ('Take Snapshot' button, summary mode) before a period closes — nothing here can reconcile a period that was never snapshotted."),
	]
	if filters.get("latest_snapshot_only"):
		parts.append(_("Showing the most recent snapshot per period only. Untick 'Latest Snapshot Only' to see every snapshot ever taken for a period (e.g. to see how the prediction itself drifted closer to the period)."))
	return "<br>".join(parts)
