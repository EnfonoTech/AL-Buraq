import frappe
from frappe.utils import cstr, flt

OPERATORS = {
	"=": lambda field_val, value: cstr(field_val) == cstr(value),
	">": lambda field_val, value: flt(field_val) > flt(value),
	"<": lambda field_val, value: flt(field_val) < flt(value),
	">=": lambda field_val, value: flt(field_val) >= flt(value),
	"<=": lambda field_val, value: flt(field_val) <= flt(value),
}


def check_approval_rules(doc, method):
	rules = frappe.get_all(
		"Approval Rule",
		filters={"reference_doctype": doc.doctype},
		fields=["fieldname", "operator", "value", "role"],
	)
	for rule in rules:
		field_val = doc.get(rule.fieldname)
		if _matches(field_val, rule.operator, rule.value):
			if rule.role not in frappe.get_roles(frappe.session.user):
				frappe.throw(frappe._("Requires {0} approval per client rule").format(rule.role))


def _matches(field_val, operator, value):
	comparator = OPERATORS.get(operator)
	if not comparator:
		frappe.throw(frappe._("Unsupported Approval Rule operator: {0}").format(operator))
	return comparator(field_val, value)
