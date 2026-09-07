// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

frappe.query_reports["Budget Suggestion"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "target_fiscal_year",
			label: __("Target Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			reqd: 1,
		},
		{
			fieldname: "history_months",
			label: __("History Months"),
			fieldtype: "Int",
			default: 12,
			reqd: 1,
			description: __("The N months immediately before the Target Fiscal Year starts. YoY Growth % needs at least 6."),
		},
		{
			fieldname: "budget_against",
			label: __("Budget Against"),
			fieldtype: "Select",
			options: ["Cost Center", "Project"],
			default: "Cost Center",
			reqd: 1,
			on_change: function () {
				frappe.query_report.set_filter_value("budget_against_filter", []);
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "budget_against_filter",
			label: __("Dimension Filter"),
			fieldtype: "MultiSelectList",
			options: "budget_against",
			get_data: function (txt) {
				let budget_against = frappe.query_report.get_filter_value("budget_against");
				if (!budget_against) return;
				return frappe.db.get_link_options(budget_against, txt, {
					company: frappe.query_report.get_filter_value("company"),
				});
			},
		},
		{
			fieldname: "account",
			label: __("Account"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Account", txt, {
					company: frappe.query_report.get_filter_value("company"),
				});
			},
		},
		{
			fieldname: "method",
			label: __("Method"),
			fieldtype: "Select",
			options: ["Moving Average", "YoY Growth %"],
			default: "Moving Average",
			reqd: 1,
			description: __("Moving Average: trailing history annualised, no growth applied. YoY Growth %: growth rate observed between the older and newer half of the history window, projected forward."),
		},
		{
			fieldname: "round_to_nearest",
			label: __("Round To Nearest"),
			fieldtype: "Select",
			options: ["1", "10", "100", "1000"],
			default: "100",
		},
		{
			fieldname: "min_amount",
			label: __("Minimum Suggested Amount"),
			fieldtype: "Currency",
			default: 0,
		},
		{
			fieldname: "include_unbudgeted_accounts",
			label: __("Include Unbudgeted Accounts"),
			fieldtype: "Check",
			default: 1,
		},
	],
	onload: function (report) {
		if (!frappe.perm.has_perm("Budget", 0, "create")) {
			return;
		}
		report.page.add_inner_button(__("Create Draft Budgets"), function () {
			frappe.confirm(
				__("This creates new DRAFT (unsubmitted) Budget records from the rows currently shown. Existing Budgets for the same dimension/year are skipped. Continue?"),
				function () {
					frappe.call({
						method: "al_buraq.api.budget_tools.create_draft_budgets_from_suggestion",
						args: { filters: frappe.query_report.get_filter_values() },
						freeze: true,
						freeze_message: __("Creating draft budgets..."),
						callback: function (r) {
							if (!r.message) return;
							let { created, skipped } = r.message;
							frappe.msgprint({
								title: __("Draft Budgets"),
								message: __("Created: {0}<br>Skipped (already has a Budget): {1}", [
									(created || []).length,
									(skipped || []).length,
								]),
								indicator: "green",
							});
						},
					});
				}
			);
		});
	},
};
