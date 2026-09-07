// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

frappe.query_reports["Rolling Forecast"] = {
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
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			reqd: 1,
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
			fieldname: "period",
			label: __("Period"),
			fieldtype: "Select",
			options: [
				{ value: "Monthly", label: __("Monthly") },
				{ value: "Quarterly", label: __("Quarterly") },
				{ value: "Half-Yearly", label: __("Half-Yearly") },
				{ value: "Yearly", label: __("Yearly") },
			],
			default: "Quarterly",
			reqd: 1,
		},
		{
			fieldname: "actual_upto",
			label: __("Actual Upto"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "forecast_version",
			label: __("Forecast Version"),
			fieldtype: "Data",
			description: __("Leave blank to use every active Forecast Revision"),
		},
		{
			fieldname: "compare_forecast_version",
			label: __("Compare Against Forecast Version"),
			fieldtype: "Data",
			description: __("Optional — adds Previous Forecast and Change vs Previous Forecast columns, re-scored at the same Actual Upto date, so this cycle's forecast can be compared against the last one."),
		},
		{
			fieldname: "commitment_basis",
			label: __("Commitment Basis"),
			fieldtype: "Select",
			options: ["Expected Date", "Transaction Date"],
			default: "Expected Date",
		},
		{
			fieldname: "current_period_basis",
			label: __("Current Period Basis"),
			fieldtype: "Select",
			options: ["Pro-rated Blend", "Actual Only", "Forecast Only"],
			default: "Pro-rated Blend",
		},
		{
			fieldname: "show_actual_forecast_split",
			label: __("Show Actual/Forecast Split"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "show_budget",
			label: __("Show Budget"),
			fieldtype: "Check",
			default: 1,
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname === "full_year_variance" && data.full_year_variance > 0) {
			value = "<span style='color:var(--red-500)'>" + value + "</span>";
		}
		if (column.fieldname === "forecast_revision_amount" && data.forecast_revision_amount > 0) {
			value = "<span style='color:var(--orange-500)'>" + value + "</span>";
		}

		return value;
	},
};
