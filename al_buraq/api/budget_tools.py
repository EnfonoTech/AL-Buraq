import frappe
from frappe import _
from frappe.utils import cint

from al_buraq.al_buraq.report.budget_suggestion.budget_suggestion import execute as run_budget_suggestion


@frappe.whitelist()
def create_draft_budgets_from_suggestion(filters):
    """
    Create draft (never-submitted) Budget records from the Budget
    Suggestion report, one per dimension found in the current filters.
    Re-runs the report server-side rather than trusting client-supplied
    amounts. Skips any dimension that already has a Budget for the
    target fiscal year.
    """
    if not frappe.has_permission("Budget", "create"):
        frappe.throw(_("Not permitted to create Budget"), frappe.PermissionError)

    filters = frappe.parse_json(filters) if isinstance(filters, str) else frappe._dict(filters or {})
    filters = frappe._dict(filters)

    columns, rows, message = run_budget_suggestion(filters)[:3]

    by_dimension = {}
    for row in rows:
        by_dimension.setdefault(row["dimension"], []).append(row)

    if len(by_dimension) > 100:
        frappe.enqueue(
            _create_draft_budgets,
            queue="long",
            timeout=1500,
            enqueue_after_commit=True,
            filters=filters,
            by_dimension=by_dimension,
        )
        return {"created": [], "skipped": [], "queued": True}

    return _create_draft_budgets(filters, by_dimension)


def _create_draft_budgets(filters, by_dimension):
    created = []
    skipped = []

    for dimension, rows in by_dimension.items():
        existing = frappe.db.exists(
            "Budget",
            {
                "company": filters.company,
                "fiscal_year": filters.target_fiscal_year,
                "budget_against": filters.budget_against,
                frappe.scrub(filters.budget_against): dimension,
                "docstatus": ["!=", 2],
            },
        )
        if existing:
            skipped.append(dimension)
            continue

        budget = frappe.get_doc(
            {
                "doctype": "Budget",
                "company": filters.company,
                "fiscal_year": filters.target_fiscal_year,
                "budget_against": filters.budget_against,
                frappe.scrub(filters.budget_against): dimension,
                "accounts": [
                    {"account": row["account"], "budget_amount": row["suggested_budget"]}
                    for row in rows
                    if cint(row["suggested_budget"])
                ],
            }
        )
        if not budget.accounts:
            skipped.append(dimension)
            continue

        budget.insert(ignore_permissions=True)
        created.append(budget.name)

    return {"created": created, "skipped": skipped, "queued": False}
