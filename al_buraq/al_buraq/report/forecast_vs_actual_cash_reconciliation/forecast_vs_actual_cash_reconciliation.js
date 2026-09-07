// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

frappe.query_reports["Forecast vs Actual Cash Reconciliation"] = {
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
			fieldname: "as_of_date",
			label: __("As Of Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
			description: __("Only snapshots whose Period End is on or before this date are shown."),
		},
		{
			fieldname: "latest_snapshot_only",
			label: __("Latest Snapshot Only"),
			fieldtype: "Check",
			default: 1,
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname === "variance" && data.variance < 0) {
			value = "<span style='color:var(--red-500)'>" + value + "</span>";
		}
		if (column.fieldname === "variance_percent" && Math.abs(data.variance_percent) >= 20) {
			value = "<span style='color:var(--orange-500);font-weight:bold'>" + value + "</span>";
		}

		return value;
	},
};
