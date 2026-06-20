import frappe


def _get_user_branch(user):
    """Return the branch name and warehouses for a user from Branch Configuration."""
    rows = frappe.get_all(
        "Branch Configuration User",
        filters={"user": user},
        fields=["parent"],
        limit=1,
    )
    if not rows:
        return None, []

    branch = rows[0].parent
    warehouses = frappe.get_all(
        "Branch Configuration Warehouse",
        filters={"parent": branch},
        pluck="warehouse",
    )
    return branch, warehouses


@frappe.whitelist()
def get_dashboard_data():
    user = frappe.session.user
    roles = set(frappe.get_roles(user))

    is_admin = bool(roles & {"System Manager", "Stock Manager"})
    is_branch_user = "Branch User" in roles
    is_stock_user = "Stock User" in roles
    is_accounts = "Accounts Manager" in roles

    branch_name, warehouses = _get_user_branch(user)

    company = (
        frappe.defaults.get_user_default("company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
    )
    currency = frappe.db.get_value("Company", company, "default_currency") or "SAR"

    today = frappe.utils.today()
    first_of_month = frappe.utils.get_first_day(today)

    data = {
        "company": company,
        "currency": currency,
        "branch_name": branch_name,
        "is_admin": is_admin,
        "is_branch_user": is_branch_user,
        "is_stock_user": is_stock_user,
        "is_accounts": is_accounts,
        "warehouses": warehouses,
    }

    # ── Sales KPIs ──────────────────────────────────────────────────────────
    if is_branch_user or is_admin:
        wh_filter = ""
        wh_params = []
        if warehouses and not is_admin:
            placeholders = ", ".join(["%s"] * len(warehouses))
            wh_filter = f"AND set_warehouse IN ({placeholders})"
            wh_params = list(warehouses)

        data["daily_sales"] = frappe.db.sql(
            f"SELECT COALESCE(SUM(grand_total),0) FROM `tabSales Invoice` "
            f"WHERE posting_date=%s AND docstatus=1 AND is_return=0 {wh_filter}",
            tuple([today] + wh_params),
        )[0][0] or 0

        data["monthly_sales"] = frappe.db.sql(
            f"SELECT COALESCE(SUM(grand_total),0) FROM `tabSales Invoice` "
            f"WHERE posting_date>=%s AND posting_date<=%s AND docstatus=1 AND is_return=0 {wh_filter}",
            tuple([first_of_month, today] + wh_params),
        )[0][0] or 0

        data["mtd_invoices"] = frappe.db.sql(
            f"SELECT COUNT(*) FROM `tabSales Invoice` "
            f"WHERE posting_date>=%s AND docstatus=1 AND is_return=0 {wh_filter}",
            tuple([first_of_month] + wh_params),
        )[0][0] or 0

        data["credits_outstanding"] = frappe.db.sql(
            f"SELECT COALESCE(SUM(outstanding_amount),0) FROM `tabSales Invoice` "
            f"WHERE docstatus=1 AND outstanding_amount>0 {wh_filter}",
            tuple(wh_params),
        )[0][0] or 0

        data["daily_returns"] = frappe.db.sql(
            f"SELECT COALESCE(SUM(grand_total),0) FROM `tabSales Invoice` "
            f"WHERE posting_date=%s AND docstatus=1 AND is_return=1 {wh_filter}",
            tuple([today] + wh_params),
        )[0][0] or 0

    # ── Purchase KPIs ────────────────────────────────────────────────────────
    if is_accounts or is_admin:
        data["monthly_purchase"] = frappe.db.sql(
            "SELECT COALESCE(SUM(grand_total),0) FROM `tabPurchase Invoice` "
            "WHERE posting_date>=%s AND posting_date<=%s AND docstatus=1 AND is_return=0",
            (first_of_month, today),
        )[0][0] or 0

        data["payables_outstanding"] = frappe.db.sql(
            "SELECT COALESCE(SUM(outstanding_amount),0) FROM `tabPurchase Invoice` "
            "WHERE docstatus=1 AND outstanding_amount>0",
        )[0][0] or 0

    # ── Stock KPIs ───────────────────────────────────────────────────────────
    if is_stock_user or is_admin:
        data["total_items"] = frappe.db.count("Item", {"disabled": 0, "is_stock_item": 1})

        data["pending_mrs"] = frappe.db.sql(
            "SELECT COUNT(*) FROM `tabMaterial Request` "
            "WHERE docstatus=1 AND status IN ('Pending','Partially Ordered') "
            "AND material_request_type='Material Transfer'",
        )[0][0] or 0

        # Pending MR list
        data["pending_mr_list"] = frappe.db.sql(
            """SELECT name, set_warehouse, set_from_warehouse,
                      transaction_date, status, material_request_type
               FROM `tabMaterial Request`
               WHERE docstatus=1 AND status IN ('Pending','Partially Ordered')
               AND material_request_type='Material Transfer'
               ORDER BY transaction_date DESC LIMIT 10""",
            as_dict=True,
        )

    return data
