import frappe
from frappe.model.document import Document


class ApprovalRule(Document):
	def validate(self):
		if not frappe.get_meta(self.reference_doctype).has_field(self.fieldname):
			frappe.throw(
				frappe._("{0} has no field named {1}").format(self.reference_doctype, self.fieldname)
			)
