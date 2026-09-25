// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

frappe.query_reports["Recurring Cash Commitment Register"] = {
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
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
			get_query: function () {
				return { filters: { company: frappe.query_report.get_filter_value("company") } };
			},
		},
		{
			fieldname: "direction",
			label: __("Direction"),
			fieldtype: "Select",
			options: "\nIn\nOut",
		},
		{
			fieldname: "classification",
			label: __("Classification"),
			fieldtype: "Select",
			options: "\nOperating\nInvesting\nFinancing\nVAT/ZATCA Settlement",
		},
		{
			fieldname: "confidence",
			label: __("Confidence"),
			fieldtype: "Select",
			options: "\nConfirmed\nProbable\nTentative",
		},
		{
			fieldname: "frequency",
			label: __("Frequency"),
			fieldtype: "Select",
			options: "\nWeekly\nMonthly\nQuarterly\nAnnually\nOne-Time",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nActive\nInactive",
			default: "Active",
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname === "direction" && data.direction === "Out") {
			value = "<span style='color:var(--red-500)'>" + value + "</span>";
		}
		if (column.fieldname === "direction" && data.direction === "In") {
			value = "<span style='color:var(--green-500)'>" + value + "</span>";
		}
		if (column.fieldname === "is_active" && !data.is_active) {
			value = "<span style='color:var(--gray-500)'>" + value + "</span>";
		}

		return value;
	},
};
