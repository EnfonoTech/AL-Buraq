import frappe
from frappe import _
from frappe.utils import flt, getdate


@frappe.whitelist()
def create_expiry_offer(item_code, discount_percent, valid_upto, company=None):
	"""Draft a Pricing Rule for stock that is close to expiry (requirement 3.2.1).

	The rule is created disabled, so nothing changes on a quotation until someone reviews it and
	switches it on. It runs until the batch expires.
	"""
	if not frappe.has_permission("Pricing Rule", "create"):
		frappe.throw(_("Not permitted to create Pricing Rules"), frappe.PermissionError)
	if not frappe.db.exists("Item", item_code):
		frappe.throw(_("Item {0} does not exist").format(item_code))

	discount = flt(discount_percent)
	if not 0 < discount <= 100:
		frappe.throw(_("The discount must be between 0 and 100"))

	company = company or frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
	currency = (company and frappe.db.get_value("Company", company, "default_currency")) or frappe.db.get_single_value(
		"Global Defaults", "default_currency"
	)

	rule = frappe.get_doc(
		{
			"doctype": "Pricing Rule",
			"title": _("Expiry offer {0}").format(item_code),
			"apply_on": "Item Code",
			"items": [{"item_code": item_code}],
			"selling": 1,
			"price_or_product_discount": "Price",
			"rate_or_discount": "Discount Percentage",
			"discount_percentage": discount,
			"valid_upto": getdate(valid_upto),
			"company": company,
			"currency": currency,
			"disable": 1,
		}
	)
	rule.insert()
	return rule.name
