# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from al_buraq.utils.approval_rules import check_approval_rules


class ForecastRevision(Document):
	def validate(self):
		self._validate_dimension()
		self._validate_accounts()
		self._validate_no_duplicate_lines()
		self._check_approval_rules_on_transition()
		self._validate_active_requires_approval()
		self._validate_unique_active_document()
		self._set_title_and_total()

	def _validate_active_requires_approval(self):
		if self.is_active and self.status != "Approved":
			frappe.throw(_("Only an Approved Forecast Revision can be set as the Active version"))

	def _check_approval_rules_on_transition(self):
		before_save = self.get_doc_before_save()
		previous_status = before_save.status if before_save else None
		if self.status == "Approved" and previous_status != "Approved":
			check_approval_rules(self, "on_approve")
			self.is_active = 1

	def _validate_dimension(self):
		if self.budget_against == "Cost Center":
			if not self.cost_center:
				frappe.throw(_("Cost Center is mandatory when Budget Against is Cost Center"))
			self.project = None
			dimension_company = frappe.db.get_value("Cost Center", self.cost_center, "company")
		else:
			if not self.project:
				frappe.throw(_("Project is mandatory when Budget Against is Project"))
			self.cost_center = None
			dimension_company = frappe.db.get_value("Project", self.project, "company")

		if dimension_company and dimension_company != self.company:
			frappe.throw(
				_("{0} {1} does not belong to Company {2}").format(
					self.budget_against, self.get(frappe.scrub(self.budget_against)), self.company
				)
			)

	def _validate_accounts(self):
		accounts = list({d.account for d in self.forecast_lines if d.account})
		if not accounts:
			return

		account_details = {
			d.name: d
			for d in frappe.get_all(
				"Account",
				filters={"name": ["in", accounts]},
				fields=["name", "company", "is_group", "root_type"],
			)
		}

		for row in self.forecast_lines:
			detail = account_details.get(row.account)
			if not detail:
				frappe.throw(_("Row {0}: Account {1} does not exist").format(row.idx, row.account))
			if detail.company != self.company:
				frappe.throw(
					_("Row {0}: Account {1} does not belong to Company {2}").format(row.idx, row.account, self.company)
				)
			if detail.is_group:
				frappe.throw(_("Row {0}: Forecast cannot be entered against Group Account {1}").format(row.idx, row.account))
			if detail.root_type not in ("Expense", "Income"):
				frappe.throw(
					_("Row {0}: Account {1} must be an Expense or Income account").format(row.idx, row.account)
				)

	def _validate_no_duplicate_lines(self):
		seen = set()
		for row in self.forecast_lines:
			key = (row.account, row.month)
			if key in seen:
				frappe.throw(_("Row {0}: Duplicate entry for Account {1} in {2}").format(row.idx, row.account, row.month))
			seen.add(key)

	def _validate_unique_active_document(self):
		if not self.is_active:
			return

		dimension_field = frappe.scrub(self.budget_against)
		existing = frappe.db.get_value(
			"Forecast Revision",
			{
				"company": self.company,
				"fiscal_year": self.fiscal_year,
				"budget_against": self.budget_against,
				dimension_field: self.get(dimension_field),
				"forecast_version": self.forecast_version,
				"is_active": 1,
				"name": ["!=", self.name],
			},
			"name",
		)
		if existing:
			frappe.throw(
				_("An active Forecast Revision {0} already exists for this {1}, Fiscal Year and Version").format(
					frappe.utils.get_link_to_form("Forecast Revision", existing), self.budget_against
				)
			)

	def _set_title_and_total(self):
		dimension_value = self.cost_center or self.project
		self.title = f"{dimension_value} - {self.fiscal_year} - {self.forecast_version}"
		self.total_forecast_amount = sum(flt(row.forecast_amount) for row in self.forecast_lines)
