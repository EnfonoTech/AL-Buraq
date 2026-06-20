import frappe
from frappe.model.document import Document


class BranchConfiguration(Document):
	def validate(self):
		self._validate_unique_users()

	def _validate_unique_users(self):
		seen = set()
		for row in self.user or []:
			if row.user in seen:
				frappe.throw(
					frappe._("User {0} added more than once in the Users table.").format(row.user)
				)
			seen.add(row.user)
