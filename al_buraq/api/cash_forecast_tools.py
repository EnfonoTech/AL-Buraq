import frappe
from frappe import _
from frappe.utils import flt, nowdate

from al_buraq.al_buraq.report.cash_forecast.cash_forecast import execute as run_cash_forecast


@frappe.whitelist()
def save_cash_forecast_snapshot(filters):
    """
    Freeze the current Cash Forecast summary buckets into Cash Forecast
    Snapshot records, so the Forecast vs Actual Cash Reconciliation report
    can later compare this prediction against what really happened.
    Re-runs the report server-side rather than trusting client-supplied
    numbers. Skips the Overdue pseudo-bucket, which has no real period.
    """
    if not frappe.has_permission("Cash Forecast Snapshot", "create"):
        frappe.throw(_("Not permitted to create Cash Forecast Snapshot"), frappe.PermissionError)

    filters = frappe.parse_json(filters) if isinstance(filters, str) else frappe._dict(filters or {})
    filters = frappe._dict(filters)
    filters["show_details"] = 0

    _columns, buckets, _message, _chart = run_cash_forecast(filters)

    created = []
    for bucket in buckets:
        if not bucket.get("period_start") or not bucket.get("period_end"):
            continue

        opening_position = flt(bucket["cumulative_cash"]) - flt(bucket["net_movement"])

        snapshot = frappe.get_doc(
            {
                "doctype": "Cash Forecast Snapshot",
                "company": filters.company,
                "snapshot_date": nowdate(),
                "period_label": bucket["period"],
                "period_start": bucket["period_start"],
                "period_end": bucket["period_end"],
                "predicted_opening_position": opening_position,
                "predicted_inflow": bucket["inflow"],
                "predicted_outflow": bucket["outflow"],
            }
        )
        snapshot.insert(ignore_permissions=True)
        created.append(snapshot.name)

    return {"created": created}
