import frappe


@frappe.whitelist()
def get_target_account(mode_of_payment, company, payment_type=None):
    """Resolve the Cheques-in-Hand-style account for a Mode of Payment.

    A single Mode of Payment (e.g. "PDC") can carry two accounts: the normal
    "Default Account" (used for Receive) and "Issued Account" (used for Pay).
    Modes that only ever go one way (e.g. "PDC Received") just leave Issued
    Account blank and default_account covers both directions.
    """
    row = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": mode_of_payment, "company": company},
        ["default_account", "custom_issued_account"],
        as_dict=True,
    )
    if not row:
        return None
    if payment_type == "Pay" and row.custom_issued_account:
        return row.custom_issued_account
    return row.default_account


@frappe.whitelist()
def get_pdc_clearing_vouchers(doctype, txt, searchfield, start, page_len, filters):
    """Restrict the Payment Entry "Clearing Voucher No" link search to vouchers
    that actually touch the account configured for the PDC's Mode of Payment.

    Expects filters = {"mode_of_payment": ..., "company": ..., "payment_type": ...}.
    """
    filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    mode_of_payment = filters.get("mode_of_payment")
    company = filters.get("company")
    payment_type = filters.get("payment_type")

    target_account = get_target_account(mode_of_payment, company, payment_type)
    if not target_account:
        return []

    txt_like = f"%{txt}%"

    if doctype == "Payment Entry":
        # paid_to = money arrived into target_account = a Debit on that account.
        # paid_from = money left target_account = a Credit on that account.
        return frappe.db.sql(
            """
            select name,
                concat(
                    case when paid_to = %(account)s
                        then concat('Total Debit: ', round(paid_amount, 2))
                        else concat('Total Credit: ', round(paid_amount, 2))
                    end,
                    ' | ', posting_date
                ) as info
            from `tabPayment Entry`
            where docstatus = 1
                and payment_type = 'Internal Transfer'
                and (paid_from = %(account)s or paid_to = %(account)s)
                and name like %(txt)s
            order by posting_date desc
            limit %(page_len)s offset %(start)s
            """,
            {
                "account": target_account,
                "txt": txt_like,
                "start": start,
                "page_len": page_len,
            },
        )

    if doctype == "Journal Entry":
        return frappe.db.sql(
            """
            select je.name,
                concat(
                    case when sum(jea.debit_in_account_currency) > 0
                        then concat('Total Debit: ', round(sum(jea.debit_in_account_currency), 2))
                        else concat('Total Credit: ', round(sum(jea.credit_in_account_currency), 2))
                    end,
                    ' | ', je.posting_date
                ) as info
            from `tabJournal Entry` je
            inner join `tabJournal Entry Account` jea
                on jea.parent = je.name and jea.account = %(account)s
            where je.docstatus = 1
                and je.name like %(txt)s
            group by je.name, je.posting_date
            order by je.posting_date desc
            limit %(page_len)s offset %(start)s
            """,
            {
                "account": target_account,
                "txt": txt_like,
                "start": start,
                "page_len": page_len,
            },
        )

    return []
