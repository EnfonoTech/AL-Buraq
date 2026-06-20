import frappe


@frappe.whitelist()
def get_sales_history(customer, limit=20):
    """Return recent Sales Invoices for a customer with line items."""
    if not customer:
        return []

    invoices = frappe.db.sql(
        """
        SELECT name, posting_date, grand_total, outstanding_amount, status
        FROM `tabSales Invoice`
        WHERE customer = %s AND docstatus = 1
        ORDER BY posting_date DESC, creation DESC
        LIMIT %s
        """,
        (customer, int(limit)),
        as_dict=True,
    )

    if not invoices:
        return []

    invoice_names = [inv.name for inv in invoices]
    items = frappe.db.sql(
        """
        SELECT parent, item_code, item_name, qty, uom, rate, amount
        FROM `tabSales Invoice Item`
        WHERE parent IN %(names)s
        ORDER BY parent, idx
        """,
        {"names": invoice_names},
        as_dict=True,
    )

    items_by_invoice = {}
    for item in items:
        items_by_invoice.setdefault(item.parent, []).append(item)

    for inv in invoices:
        inv["items"] = items_by_invoice.get(inv.name, [])

    return invoices


@frappe.whitelist()
def get_purchase_history(supplier, limit=20):
    """Return recent Purchase Invoices for a supplier with line items."""
    if not supplier:
        return []

    invoices = frappe.db.sql(
        """
        SELECT name, posting_date, grand_total, outstanding_amount, status
        FROM `tabPurchase Invoice`
        WHERE supplier = %s AND docstatus = 1
        ORDER BY posting_date DESC, creation DESC
        LIMIT %s
        """,
        (supplier, int(limit)),
        as_dict=True,
    )

    if not invoices:
        return []

    invoice_names = [inv.name for inv in invoices]
    items = frappe.db.sql(
        """
        SELECT parent, item_code, item_name, qty, uom, rate, amount
        FROM `tabPurchase Invoice Item`
        WHERE parent IN %(names)s
        ORDER BY parent, idx
        """,
        {"names": invoice_names},
        as_dict=True,
    )

    items_by_invoice = {}
    for item in items:
        items_by_invoice.setdefault(item.parent, []).append(item)

    for inv in invoices:
        inv["items"] = items_by_invoice.get(inv.name, [])

    return invoices
