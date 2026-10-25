import frappe

# Requirement 1.1 (and 3.2.1 for the batch rule): reminders the site starts with. Everyone can edit,
# disable or delete them under Document Reminder Rule.
DEFAULT_RULES = [
	{
		"rule_name": "Purchase Orders due for delivery",
		"document_type": "Purchase Order",
		"date_field": "schedule_date",
		"when": "Before",
		"days": 2,
		"filters": '[["docstatus", "=", 1], ["status", "in", ["To Receive and Bill", "To Receive"]]]',
		"roles": ["Purchase Manager"],
		"notify_owner": 1,
		"subject": "{count} Purchase Orders due for delivery within {days} days",
	},
	{
		"rule_name": "Purchase Invoices due for payment",
		"document_type": "Purchase Invoice",
		"date_field": "due_date",
		"when": "Before",
		"days": 3,
		"filters": '[["docstatus", "=", 1], ["outstanding_amount", ">", 0]]',
		"roles": ["Accounts Manager"],
		"notify_owner": 0,
		"subject": "{count} Purchase Invoices to pay within {days} days",
	},
	{
		"rule_name": "Sales Invoices overdue",
		"document_type": "Sales Invoice",
		"date_field": "due_date",
		"when": "After",
		"days": 1,
		"filters": '[["docstatus", "=", 1], ["outstanding_amount", ">", 0]]',
		"roles": ["Accounts Manager", "Sales Manager"],
		"notify_owner": 0,
		"subject": "{count} Sales Invoices overdue by {days} days or more",
		# Shipped switched off: on the day this went in, 248 of the 265 invoices were overdue, so the
		# digest would repeat the same big number every morning. Switch it on once receivables are tidy.
		"enabled": 0,
	},
	{
		"rule_name": "Delivery Notes not yet submitted",
		"document_type": "Delivery Note",
		"date_field": "posting_date",
		"when": "After",
		"days": 1,
		"filters": '[["docstatus", "=", 0]]',
		"roles": ["Stock Manager"],
		"notify_owner": 1,
		"subject": "{count} Delivery Notes still in draft after {days} day(s)",
	},
	{
		"rule_name": "Quotations about to expire",
		"document_type": "Quotation",
		"date_field": "valid_till",
		"when": "Before",
		"days": 2,
		"filters": '[["status", "in", ["Open", "Replied", "Partially Ordered"]]]',
		"roles": ["Sales Manager"],
		"notify_owner": 1,
		"subject": "{count} Quotations expire within {days} days",
	},
	{
		"rule_name": "Batches about to expire",
		"document_type": "Batch",
		"date_field": "expiry_date",
		"when": "Before",
		"days": 30,
		"filters": '[["disabled", "=", 0], ["batch_qty", ">", 0]]',
		"roles": ["Stock Manager"],
		"notify_owner": 0,
		"subject": "{count} batches expire within {days} days",
	},
]

DEFAULT_TIERS = [(30, 20), (60, 10)]


def execute():
	seed_expiry_tiers()
	for spec in DEFAULT_RULES:
		if frappe.db.exists("Document Reminder Rule", spec["rule_name"]):
			continue
		try:
			rule = frappe.get_doc(
				{
					"doctype": "Document Reminder Rule",
					"enabled": 1,
					**{k: v for k, v in spec.items() if k != "roles"},
					"roles": [{"role": r} for r in spec["roles"] if frappe.db.exists("Role", r)],
				}
			)
			rule.insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(title=f"Default reminder rule {spec['rule_name']} not created")


def seed_expiry_tiers():
	settings = frappe.get_doc("Al Buraq Settings")
	if settings.get("expiry_offer_tiers"):
		return
	for days, discount in DEFAULT_TIERS:
		settings.append("expiry_offer_tiers", {"days_to_expiry": days, "discount_percent": discount})
	settings.save(ignore_permissions=True)
