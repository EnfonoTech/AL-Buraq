# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from al_buraq.utils.approval_rules import check_approval_rules

# Specificity score used both by validate() (for the overlap warning) and
# by the Budget Scenario Comparison report (for deterministic application
# order): more specific scopes win, Absolute Override always applies last.
SPECIFICITY = {
	"Cost Center + Account": 4,
	"Project + Account": 4,
	"Account": 3,
	"Cost Center": 2,
	"Project": 2,
	"All": 1,
}


class BudgetScenario(Document):
	def validate(self):
		self._validate_dimensions()
		self._validate_scope_rules()
		self._validate_no_duplicate_lines()
		self._warn_on_overlaps()
		self._check_approval_rules_on_transition()

	def _check_approval_rules_on_transition(self):
		before_save = self.get_doc_before_save()
		previous_status = before_save.status if before_save else None
		if self.status == "Approved" and previous_status != "Approved":
			check_approval_rules(self, "on_approve")

	def _validate_dimensions(self):
		cost_centers = {row.cost_center for row in self.scenario_lines if row.cost_center}
		projects = {row.project for row in self.scenario_lines if row.project}
		accounts = {row.account for row in self.scenario_lines if row.account}

		if cost_centers:
			details = {
				d.name: d
				for d in frappe.get_all(
					"Cost Center", filters={"name": ["in", list(cost_centers)]}, fields=["name", "company"]
				)
			}
			for row in self.scenario_lines:
				if row.cost_center and details.get(row.cost_center, frappe._dict()).company != self.company:
					frappe.throw(
						_("Row {0}: Cost Center {1} does not belong to Company {2}").format(
							row.idx, row.cost_center, self.company
						)
					)

		if projects:
			details = {
				d.name: d
				for d in frappe.get_all("Project", filters={"name": ["in", list(projects)]}, fields=["name", "company"])
			}
			for row in self.scenario_lines:
				if row.project and details.get(row.project, frappe._dict()).company != self.company:
					frappe.throw(
						_("Row {0}: Project {1} does not belong to Company {2}").format(row.idx, row.project, self.company)
					)

		if accounts:
			details = {
				d.name: d
				for d in frappe.get_all("Account", filters={"name": ["in", list(accounts)]}, fields=["name", "company"])
			}
			for row in self.scenario_lines:
				if row.account and details.get(row.account, frappe._dict()).company != self.company:
					frappe.throw(
						_("Row {0}: Account {1} does not belong to Company {2}").format(row.idx, row.account, self.company)
					)

		dimension_field = "cost_center" if self.budget_against == "Cost Center" else "project"
		other_field = "project" if self.budget_against == "Cost Center" else "cost_center"
		dimension_scopes = (self.budget_against, f"{self.budget_against} + Account")

		for row in self.scenario_lines:
			if row.get(other_field):
				frappe.throw(
					_("Row {0}: {1} is set, but this Scenario's Budget Against is {2}").format(
						row.idx, other_field.replace("_", " ").title(), self.budget_against
					)
				)
			if row.apply_to in dimension_scopes and not row.get(dimension_field):
				frappe.throw(_("Row {0}: {1} is required for Apply To = {2}").format(row.idx, self.budget_against, row.apply_to))

	def _validate_scope_rules(self):
		for row in self.scenario_lines:
			if row.adjustment_type in ("Fixed Amount", "Absolute Override") and row.apply_to == "All":
				frappe.throw(
					_("Row {0}: {1} adjustments require a specific Cost Center, Project or Account — not 'All'").format(
						row.idx, row.adjustment_type
					)
				)
			if row.adjustment_type == "Absolute Override" and not row.account:
				frappe.throw(_("Row {0}: Absolute Override requires an Account").format(row.idx))
			if row.adjustment_type == "Percentage" and row.adjustment_value < -100:
				frappe.throw(_("Row {0}: Percentage adjustment cannot reduce below -100%").format(row.idx))
			if row.adjustment_type == "Delay in Days" and row.account:
				frappe.throw(
					_("Row {0}: Delay in Days cannot be scoped to an Account — it shifts Cash Forecast timing, not a Budget/P&L amount").format(row.idx)
				)

	def _validate_no_duplicate_lines(self):
		seen = set()
		for row in self.scenario_lines:
			key = (
				row.apply_to,
				row.cost_center,
				row.project,
				row.account,
				row.adjustment_type,
				row.party_type,
				row.period_scope,
				row.month,
			)
			if key in seen:
				frappe.throw(_("Row {0}: Duplicate scenario line").format(row.idx))
			seen.add(key)

	def _warn_on_overlaps(self):
		by_specificity = {}
		for row in self.scenario_lines:
			by_specificity.setdefault(SPECIFICITY.get(row.apply_to, 0), []).append(row.idx)

		overlaps = [rows for rows in by_specificity.values() if len(rows) > 1]
		if overlaps:
			frappe.msgprint(
				_(
					"Rows {0} share the same specificity level. Where their scopes overlap, they are applied in row order (Percentage before Fixed Amount), and Absolute Override always applies last."
				).format(", ".join(str(r) for rows in overlaps for r in rows)),
				indicator="orange",
				alert=True,
			)
