import json
import frappe
from frappe import _


@frappe.whitelist()
def get_payment_modes(company):
    """
    Return enabled Modes of Payment that have a default account for the company.
    Branch Users are restricted to the modes configured in their Branch Configuration.
    Admins/Managers see all enabled modes.
    """
    if not company:
        return []

    user = frappe.session.user
    roles = set(frappe.get_roles(user))
    is_admin = bool(roles & {"System Manager", "Stock Manager", "Sales Manager", "Accounts Manager"})

    branch_modes = None
    if not is_admin:
        rows = frappe.get_all(
            "Branch Configuration User",
            filters={"user": user},
            fields=["parent"],
            limit=1,
        )
        if rows:
            branch = rows[0].parent
            branch_modes = frappe.get_all(
                "Branch Configuration Mode of Payment",
                filters={"parent": branch},
                pluck="mode_of_payment",
            )

    # Modes that have an account for this company
    has_account = frappe.db.sql(
        "SELECT DISTINCT parent FROM `tabMode of Payment Account` "
        "WHERE company = %s AND default_account IS NOT NULL AND default_account != ''",
        (company,),
        as_list=True,
    )
    modes_with_account = {r[0] for r in has_account}

    if branch_modes is not None:
        enabled = frappe.get_all(
            "Mode of Payment",
            filters={"name": ["in", branch_modes], "enabled": 1},
            pluck="name",
        ) if branch_modes else []
    else:
        enabled = frappe.get_all("Mode of Payment", filters={"enabled": 1}, pluck="name")

    return [m for m in enabled if m in modes_with_account]


@frappe.whitelist()
def create_payment_entries(sales_invoice, payments):
    """
    Create submitted Payment Entry records for a submitted Sales Invoice,
    one per mode of payment with a non-zero amount.

    payments: JSON list of {"mode_of_payment": str, "amount": float}
    """
    if not sales_invoice:
        frappe.throw(_("Sales Invoice is required"))

    si = frappe.get_doc("Sales Invoice", sales_invoice)
    if si.docstatus != 1:
        frappe.throw(_("Sales Invoice {0} must be submitted before creating payments.").format(si.name))

    if isinstance(payments, str):
        try:
            payments = json.loads(payments)
        except Exception:
            frappe.throw(_("Invalid payments data"))

    valid_rows = [
        {"mode_of_payment": r.get("mode_of_payment"), "amount": frappe.utils.flt(r.get("amount"))}
        for r in (payments or [])
        if r.get("mode_of_payment") and frappe.utils.flt(r.get("amount")) > 0
    ]

    if not valid_rows:
        frappe.throw(_("No valid payment rows (non-zero amounts with a mode of payment)."))

    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
    from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

    created = []

    for row in valid_rows:
        si.reload()
        outstanding = frappe.utils.flt(si.outstanding_amount)
        amount = frappe.utils.flt(row["amount"])

        if amount - outstanding > 0.5:
            frappe.throw(
                _("Payment {0} exceeds outstanding {1} on invoice {2}.").format(
                    amount, outstanding, si.name
                )
            )

        pe = get_payment_entry("Sales Invoice", si.name)
        pe.mode_of_payment = row["mode_of_payment"]

        bank_cash = get_bank_cash_account(row["mode_of_payment"], si.company)
        pe.paid_to = bank_cash.get("account")

        if pe.paid_to:
            acc = frappe.get_cached_value(
                "Account", pe.paid_to, ["account_currency", "account_type"], as_dict=True
            )
            if acc:
                pe.paid_to_account_currency = acc.account_currency
                pe.paid_to_account_type = acc.account_type

        pe.paid_amount = amount
        pe.received_amount = amount

        if pe.references:
            pe.references[0].allocated_amount = amount

        pe.posting_date = pe.posting_date or si.posting_date
        pe.reference_no = si.name
        pe.reference_date = si.posting_date

        pe.insert()
        pe.submit()
        created.append(pe.name)

    return created
