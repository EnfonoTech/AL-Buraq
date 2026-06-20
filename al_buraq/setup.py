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
    ]
    for f in fields:
        if not frappe.db.exists("Custom Field", {"dt": f["dt"], "fieldname": f["fieldname"]}):
            doc = frappe.get_doc({"doctype": "Custom Field"})
            doc.update(f)
            doc.insert(ignore_permissions=True)
    frappe.db.commit()
