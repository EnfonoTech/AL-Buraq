# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class PriceandDiscountRule(Document):
	def validate(self):
		if flt(self.min_qty) < 0 or flt(self.max_qty) < 0:
			frappe.throw(_("Quantities cannot be negative"))
		if flt(self.max_qty) and flt(self.max_qty) < flt(self.min_qty):
			frappe.throw(_("Up To Quantity cannot be less than From Quantity"))

		for field in ("default_discount_percent", "max_discount_percent"):
			if not 0 <= flt(self.get(field)) <= 100:
				frappe.throw(_("{0} must be between 0 and 100").format(_(self.meta.get_label(field))))

		if flt(self.max_discount_percent) and flt(self.default_discount_percent) > flt(self.max_discount_percent):
			frappe.throw(_("The discount given automatically cannot be more than the maximum discount"))
