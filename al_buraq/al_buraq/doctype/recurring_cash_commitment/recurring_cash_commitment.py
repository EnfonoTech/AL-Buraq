# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class RecurringCashCommitment(Document):
	def validate(self):
		self._validate_dates()
		self._validate_cost_center()

	def _validate_dates(self):
		if self.frequency == "One-Time":
			self.end_date = None
		if self.end_date and getdate(self.end_date) < getdate(self.start_date):
			frappe.throw(_("End Date cannot be before Start Date"))

	def _validate_cost_center(self):
		if not self.cost_center:
			return
		cost_center_company = frappe.db.get_value("Cost Center", self.cost_center, "company")
		if cost_center_company != self.company:
			frappe.throw(_("Cost Center {0} does not belong to Company {1}").format(self.cost_center, self.company))
