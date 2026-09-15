import os
import frappe

BRANCH_CONFIG_DOCTYPES = [
    "Branch Configuration",
    "Branch Naming Series",
    "Inter Company Branch",
]

ROLE_PERMISSIONS = [
    # (role, read, write, create, delete)
    ("Stock Manager", 1, 1, 1, 0),
    ("Accounts Manager", 1, 0, 0, 0),
]


def after_install():
    _clean_stale_module()
    _force_import_doctypes()
    setup_branch_config_permissions()
    create_custom_fields()


def after_migrate():
    _clean_stale_module()
    _force_import_doctypes()
    setup_branch_config_permissions()
    create_custom_fields()


def _clean_stale_module():
    """Remove the old lowercase 'al_buraq' Module Def if it still exists."""
    if frappe.db.exists("Module Def", "al_buraq"):
        frappe.db.delete("Module Def", {"name": "al_buraq"})
        frappe.db.commit()


def _force_import_doctypes():
    """Force-import doctypes that may be left orphaned from a previous app install."""
    from frappe.modules.import_file import import_file_by_path

    orphan_prone = [
        "branch_configuration_mode_of_payment",
        "branch_naming_series",
    ]
    app_path = frappe.get_app_path("al_buraq")
    for dt in orphan_prone:
        json_path = os.path.join(app_path, "al_buraq", "doctype", dt, f"{dt}.json")
        if os.path.exists(json_path):
            try:
                import_file_by_path(json_path, force=True)
            except Exception:
                pass


def setup_branch_config_permissions():
    """Add read/write access on branch config doctypes for Stock Manager and Accounts Manager."""
    for doctype in BRANCH_CONFIG_DOCTYPES:
        if not frappe.db.exists("DocType", doctype):
            continue
        for role, read, write, create, delete in ROLE_PERMISSIONS:
            if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role}):
                frappe.get_doc({
                    "doctype": "Custom DocPerm",
                    "parent": doctype,
                    "parenttype": "DocType",
                    "parentfield": "permissions",
                    "role": role,
                    "permlevel": 0,
                    "read": read,
                    "write": write,
                    "create": create,
                    "delete": delete,
                }).insert(ignore_permissions=True)

    frappe.db.commit()


def create_custom_fields():
    """Create custom fields on standard doctypes needed by al_buraq features."""
    fields = [
        {
            "dt": "Sales Invoice",
            "fieldname": "custom_payment_mode",
            "label": "Payment Mode",
            "fieldtype": "Select",
            "options": "\nCash\nCredit",
            "insert_after": "due_date",
            "in_list_view": 0,
            "in_standard_filter": 1,
        },
        # PDC (Post-Dated Cheque) support
        {
            "dt": "Mode of Payment",
            "fieldname": "custom_is_pdc_payment",
            "label": "Is PDC Payment",
            "fieldtype": "Check",
            "insert_after": "type",
            "description": (
                "Enable this to treat this Mode of Payment as a Post-Dated Cheque mode "
                "(Payment Entry will require a clearing reference)."
            ),
        },
        {
            "dt": "Mode of Payment Account",
            "fieldname": "custom_issued_account",
            "label": "Issued Account (for PDC-style modes)",
            "fieldtype": "Link",
            "options": "Account",
            "insert_after": "default_account",
            "description": (
                "Used when a single Mode of Payment (e.g. PDC) needs a different account for "
                "Pay vs Receive. Default Account above is used for Receive."
            ),
        },
        {
            "dt": "Payment Entry",
            "fieldname": "custom_is_pdc_mode",
            "label": "Is PDC Mode",
            "fieldtype": "Check",
            "insert_after": "mode_of_payment",
            "fetch_from": "mode_of_payment.custom_is_pdc_payment",
            "hidden": 1,
            "read_only": 1,
        },
        {
            "dt": "Payment Entry",
            "fieldname": "custom_clearing_voucher_type",
            "label": "Clearing Voucher Type",
            "fieldtype": "Select",
            "options": "\nPayment Entry\nJournal Entry",
            "insert_after": "custom_is_pdc_mode",
            "depends_on": "eval:doc.custom_is_pdc_mode",
            "allow_on_submit": 1,
            "description": (
                "The voucher that moved this cheque's amount from Cheques in Hand to the real "
                "Bank account. Leave blank while the cheque is still pending."
            ),
        },
        {
            "dt": "Payment Entry",
            "fieldname": "custom_clearing_voucher_no",
            "label": "Clearing Voucher No",
            "fieldtype": "Dynamic Link",
            "options": "custom_clearing_voucher_type",
            "insert_after": "custom_clearing_voucher_type",
            "depends_on": "eval:doc.custom_is_pdc_mode",
            "allow_on_submit": 1,
        },
    ]
    for f in fields:
        if not frappe.db.exists("Custom Field", {"dt": f["dt"], "fieldname": f["fieldname"]}):
            doc = frappe.get_doc({"doctype": "Custom Field"})
            doc.update(f)
            doc.insert(ignore_permissions=True)
    frappe.db.commit()


def setup_pdc_config(company):
    """One-time PDC config for a company: a single "PDC" Mode of Payment (Received account
    used for Receive, Issued account used for Pay) + Cheques in Hand accounts.

    Disables the older "PDC Received"/"PDC Issued" modes if present (not deleted, so
    historical Payment Entries referencing them by name keep working).

    Run manually per company, e.g.:
        bench --site buraq execute al_buraq.setup.setup_pdc_config --kwargs "{'company': 'HVAC GENERAL TRADING'}"
    """
    company_doc = frappe.get_doc("Company", company)
    abbr = company_doc.abbr
    bank_group = frappe.db.get_value(
        "Account", {"company": company, "account_type": "Bank", "is_group": 1}
    )
    if not bank_group:
        frappe.throw(f"No Bank account group found for {company}")

    accounts = {}
    for label in ("Received", "Issued"):
        account_name = f"Cheques in Hand - {label} - {abbr}"
        if not frappe.db.exists("Account", account_name):
            frappe.get_doc(
                {
                    "doctype": "Account",
                    "account_name": f"Cheques in Hand - {label}",
                    "parent_account": bank_group,
                    "company": company,
                    "account_type": "Bank",
                    "account_currency": company_doc.default_currency,
                }
            ).insert(ignore_permissions=True)
        accounts[label] = account_name

    if not frappe.db.exists("Mode of Payment", "PDC"):
        frappe.get_doc(
            {
                "doctype": "Mode of Payment",
                "mode_of_payment": "PDC",
                "type": "Bank",
                "custom_is_pdc_payment": 1,
            }
        ).insert(ignore_permissions=True)
    else:
        frappe.db.set_value("Mode of Payment", "PDC", "custom_is_pdc_payment", 1)

    mop = frappe.get_doc("Mode of Payment", "PDC")
    row = next((a for a in mop.accounts if a.company == company), None)
    if not row:
        mop.append("accounts", {"company": company})
        row = mop.accounts[-1]
    row.default_account = accounts["Received"]
    row.custom_issued_account = accounts["Issued"]
    mop.save(ignore_permissions=True)

    for old_mode in ("PDC Received", "PDC Issued"):
        if frappe.db.exists("Mode of Payment", old_mode):
            frappe.db.set_value("Mode of Payment", old_mode, "enabled", 0)

    frappe.db.commit()
