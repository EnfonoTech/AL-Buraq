// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

frappe.query_reports["Scenario Impact Summary"] = {
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
			fieldname: "scenario_1",
			label: __("Scenario 1"),
			fieldtype: "Link",
			options: "Budget Scenario",
			get_query: function () {
				return {
					filters: {
						company: frappe.query_report.get_filter_value("company"),
						fiscal_year: frappe.query_report.get_filter_value("fiscal_year"),
						budget_against: "Cost Center",
					},
				};
			},
		},
		{
			fieldname: "scenario_2",
			label: __("Scenario 2"),
			fieldtype: "Link",
			options: "Budget Scenario",
			get_query: function () {
				return {
					filters: {
						company: frappe.query_report.get_filter_value("company"),
						fiscal_year: frappe.query_report.get_filter_value("fiscal_year"),
						budget_against: "Cost Center",
					},
				};
			},
		},
		{
			fieldname: "cash_horizon_days",
			label: __("Net Cash Position Horizon (Days)"),
			fieldtype: "Int",
			default: 90,
			description: __("How far out from today to project the Net Cash Position metric."),
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname && column.fieldname.endsWith("_diff") && data[column.fieldname] < 0) {
			value = "<span style='color:var(--red-500)'>" + value + "</span>";
		} else if (column.fieldname && column.fieldname.endsWith("_diff_percent") && data[column.fieldname] < 0) {
			value = "<span style='color:var(--red-500)'>" + value + "</span>";
		}

		return value;
	},
};
