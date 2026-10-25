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


# Permission level that guards the internal profit block on Quotation. Level 1 is already used by
# ERPNext for Sales User / Maintenance roles, so profit gets its own level; the roles that may read
# it are granted by patches/grant_quotation_profit_permlevel.py.
PROFIT_PERMLEVEL = 2

# Requirements 2.1.2 (Quotation profit), 2.1.3 (temporary items), 3.1.3 (maximum selling rate).
BATCH1_CUSTOM_FIELDS = [
    {
        "dt": "Quotation",
        "fieldname": "custom_profit_section",
        "label": "Profit (internal)",
        "fieldtype": "Section Break",
        "insert_after": "items",
        "permlevel": PROFIT_PERMLEVEL,
    },
    {
        "dt": "Quotation",
        "fieldname": "custom_total_profit",
        "label": "Total Profit",
        "fieldtype": "Currency",
        "options": "Company:company:default_currency",
        "insert_after": "custom_profit_section",
        "read_only": 1,
        "permlevel": PROFIT_PERMLEVEL,
        "description": "Net selling total less item cost, in company currency. Recalculated on save.",
    },
    {
        "dt": "Quotation",
        "fieldname": "custom_profit_column",
        "fieldtype": "Column Break",
        "insert_after": "custom_total_profit",
        "permlevel": PROFIT_PERMLEVEL,
    },
    {
        "dt": "Quotation",
        "fieldname": "custom_profit_percent",
        "label": "Profit %",
        "fieldtype": "Percent",
        "insert_after": "custom_profit_column",
        "read_only": 1,
        "permlevel": PROFIT_PERMLEVEL,
        "description": "Total Profit as a percentage of the net selling total.",
    },
    {
        "dt": "Quotation",
        "fieldname": "custom_profit_note",
        "label": "Profit Note",
        "fieldtype": "Small Text",
        "insert_after": "custom_profit_percent",
        "read_only": 1,
        "permlevel": PROFIT_PERMLEVEL,
    },
    {
        "dt": "Item",
        "fieldname": "custom_is_temporary",
        "label": "Temporary Item",
        "fieldtype": "Check",
        "insert_after": "disabled",
        "read_only": 1,
        "in_standard_filter": 1,
        "description": (
            "Created from a Quotation for a product that is not in stock yet. Cleared automatically "
            "when stock is received, or merge it into the real item."
        ),
    },
    {
        "dt": "Item",
        "fieldname": "custom_temp_quotation",
        "label": "Created From Quotation",
        "fieldtype": "Data",
        "insert_after": "custom_is_temporary",
        "read_only": 1,
        "depends_on": "eval:doc.custom_temp_quotation",
    },
    {
        "dt": "Item",
        "fieldname": "custom_temp_received_on",
        "label": "Stock Received On",
        "fieldtype": "Date",
        "insert_after": "custom_temp_quotation",
        "read_only": 1,
        "depends_on": "eval:doc.custom_temp_received_on",
    },
    {
        "dt": "Item",
        "fieldname": "custom_max_selling_rate",
        "label": "Maximum Selling Rate",
        "fieldtype": "Currency",
        "insert_after": "max_discount",
        "description": (
            "Highest selling rate allowed for this item. Standard Selling Rate and selling Item Prices "
            "cannot exceed it. Leave 0 for no limit."
        ),
    },
]


# Requirement 2.4.1: a row remembers the Price and Discount Rule that filled its discount, so the
# rule is applied once and a salesperson who sets the discount back to 0 keeps 0.
BATCH3_CUSTOM_FIELDS = [
    {
        "dt": dt,
        "fieldname": "custom_rule_applied",
        "label": "Discount Rule Applied",
        "fieldtype": "Data",
        "insert_after": "discount_percentage",
        "hidden": 1,
        "read_only": 1,
        "no_copy": 1,
        "print_hide": 1,
    }
    for dt in ("Quotation Item", "Sales Order Item", "Sales Invoice Item")
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
    fields += BATCH1_CUSTOM_FIELDS + BATCH3_CUSTOM_FIELDS
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
