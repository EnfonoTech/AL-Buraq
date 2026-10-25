# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from al_buraq.tasks.document_reminders import parse_filters

DATE_FIELDTYPES = ("Date", "Datetime")


class DocumentReminderRule(Document):
	def validate(self):
		field = frappe.get_meta(self.document_type).get_field(self.date_field)
		if not field and self.date_field not in ("creation", "modified"):
			frappe.throw(
				_("{0} has no field called {1}").format(frappe.bold(self.document_type), frappe.bold(self.date_field))
			)
		if field and field.fieldtype not in DATE_FIELDTYPES:
			frappe.throw(_("{0} is not a date field").format(frappe.bold(self.date_field)))

		if cint(self.days) < 0:
			frappe.throw(_("Days cannot be negative"))

		try:
			parse_filters(self.filters)
		except ValueError as e:
			frappe.throw(_("Only Documents Matching: {0}").format(str(e)))

		if not self.get("roles") and not self.notify_owner:
			frappe.throw(_("Choose who is told: a role, the document owner, or both"))
