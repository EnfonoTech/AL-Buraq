# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class CashForecastSnapshot(Document):
	def validate(self):
		self._validate_period()
		self._set_derived_fields()

	def _validate_period(self):
		if getdate(self.period_end) < getdate(self.period_start):
			frappe.throw(_("Period End cannot be before Period Start"))

	def _set_derived_fields(self):
		self.predicted_net_movement = flt(self.predicted_inflow) - flt(self.predicted_outflow)
		self.predicted_closing_position = flt(self.predicted_opening_position) + self.predicted_net_movement
		if not self.period_label:
			self.period_label = f"{self.period_start} - {self.period_end}"
