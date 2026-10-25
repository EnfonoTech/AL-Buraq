# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today

# A job in either of these is moved by hand; every other status follows its stages.
MANUAL_STATUSES = ("On Hold", "Cancelled")


class JobRecord(Document):
	def validate(self):
		self.update_stages_and_progress()

	def before_update_after_submit(self):
		# stages are edited after submit, and validate does not run for that save
		self.update_stages_and_progress()

	def update_stages_and_progress(self):
		seen = set()
		for stage in self.get("stages") or []:
			if stage.department in seen:
				frappe.throw(
					_("Row {0}: department {1} is already a stage of this job").format(
						stage.idx, frappe.bold(stage.department)
					)
				)
			seen.add(stage.department)

			if stage.start_date and stage.end_date and getdate(stage.end_date) < getdate(stage.start_date):
				frappe.throw(_("Row {0}: end date cannot be before the start date").format(stage.idx))

			if stage.status == "In Progress" and not stage.start_date:
				stage.start_date = today()
			if stage.status == "Done":
				stage.start_date = stage.start_date or today()
				stage.end_date = stage.end_date or today()

		stages = self.get("stages") or []
		done = sum(1 for s in stages if s.status == "Done")
		self.progress = flt(done / len(stages) * 100, 2) if stages else 0

		if self.status in MANUAL_STATUSES:
			return
		if stages and done == len(stages):
			self.status = "Completed"
		elif any(s.status in ("In Progress", "Done", "Blocked") for s in stages):
			self.status = "In Progress"
		else:
			self.status = "Open"
