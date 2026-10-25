import frappe
from frappe import _
from frappe.utils import cint, flt

MANAGER_ROLES = {"Sales Manager", "System Manager"}
RULE_FIELDS = [
	"name",
	"priority",
	"company",
	"item_group",
	"customer_group",
	"min_qty",
	"max_qty",
	"default_discount_percent",
	"max_discount_percent",
]


def apply_default_discount(doc, method=None):
	"""before_validate on Quotation, Sales Order and Sales Invoice (requirement 2.4.1).

	A row with no discount gets the discount ratio of the best matching Price and Discount Rule. It
	is applied once per row: the row remembers the rule, so a salesperson who sets it back to 0
	keeps 0. Runs before ERPNext totals the document, so the rate follows.
	"""
	rules = enabled_rules()
	if not rules:
		return

	customer_group = customer_group_of(doc)
	for row in doc.get("items") or []:
		if row.get("custom_rule_applied") or flt(row.discount_percentage) or flt(row.discount_amount):
			continue
		if not flt(row.price_list_rate):
			continue
		rule = best_rule(rules, doc, row, customer_group)
		if rule and flt(rule.default_discount_percent):
			row.discount_percentage = flt(rule.default_discount_percent)
			row.custom_rule_applied = rule.name


def check_max_discount(doc, method=None):
	"""validate: a row's discount may not exceed the maximum of its rule. Sales Managers, and a
	document with the manager override ticked, may go over."""
	if MANAGER_ROLES & set(frappe.get_roles()) or doc.get("custom_manager_override"):
		return
	rules = enabled_rules()
	if not rules:
		return

	customer_group = customer_group_of(doc)
	for row in doc.get("items") or []:
		rule = best_rule(rules, doc, row, customer_group)
		if not rule or not flt(rule.max_discount_percent):
			continue
		given = effective_discount(row)
		if given > flt(rule.max_discount_percent) + 0.0001:
			frappe.throw(
				_("Row {0}: a discount of {1}% is more than the {2}% allowed for {3} (rule {4}). A Sales Manager can approve it.").format(
					row.idx, flt(given, 2), flt(rule.max_discount_percent), frappe.bold(row.item_code), rule.name
				)
			)


def effective_discount(row):
	"""The discount of a row as a percentage. ERPNext totals a row from its discount percentage (the
	form turns a typed amount or rate into a percentage), so that is the figure to hold to a maximum."""
	return flt(row.discount_percentage)


def enabled_rules():
	return frappe.get_all("Price and Discount Rule", filters={"enabled": 1}, fields=RULE_FIELDS)


def customer_group_of(doc):
	if doc.get("customer_group"):
		return doc.customer_group
	if doc.doctype == "Quotation" and doc.get("quotation_to") == "Customer" and doc.get("party_name"):
		return frappe.db.get_value("Customer", doc.party_name, "customer_group")
	return None


def item_group_of(row):
	return row.get("item_group") or (row.get("item_code") and frappe.db.get_value("Item", row.item_code, "item_group"))


def best_rule(rules, doc, row, customer_group):
	"""The most specific matching rule: one naming the item group counts 2, one naming the customer
	group counts 1; equally specific rules go by priority (higher first), then by name."""
	item_group = item_group_of(row)
	qty = flt(row.get("qty"))
	matches = []
	for rule in rules:
		if rule.company and rule.company != doc.get("company"):
			continue
		if rule.item_group and rule.item_group != item_group:
			continue
		if rule.customer_group and rule.customer_group != customer_group:
			continue
		if qty < flt(rule.min_qty) or (flt(rule.max_qty) and qty > flt(rule.max_qty)):
			continue
		matches.append(rule)

	if not matches:
		return None
	return min(
		matches,
		key=lambda r: (-((2 if r.item_group else 0) + (1 if r.customer_group else 0)), -cint(r.priority), r.name),
	)
