// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

frappe.query_reports["Job Tracker"] = {
	filters: [
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nOpen\nIn Progress\nOn Hold\nCompleted\nCancelled" },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
		{ fieldname: "show_completed", label: __("Include Completed"), fieldtype: "Check", default: 0 },
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		const colours = { Done: "green", "In Progress": "blue", Blocked: "red", Pending: "gray" };
		const text = data && data[column.fieldname];
		if (column.fieldname.startsWith("dept_") && colours[text]) {
			return `<span class="indicator-pill ${colours[text]}">${__(text)}</span>`;
		}
		return value;
	},
};
