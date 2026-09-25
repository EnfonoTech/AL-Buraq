// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

frappe.query_reports["Pending PDC Details"] = {
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
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), 30),
			reqd: 1,
		},
		{
			fieldname: "source",
			label: __("Source"),
			fieldtype: "Select",
			options: "\nPDC\nRecurring Commitment",
			description: __("Recurring Commitment here means expense (Direction=Out) occurrences from Recurring Cash Commitment, projected forward the same way Cash Forecast does."),
		},
		{
			fieldname: "direction",
			label: __("Direction"),
			fieldtype: "Select",
			options: "\nIn\nOut",
		},
		{
			fieldname: "party_type",
			label: __("Party Type"),
			fieldtype: "Link",
			options: "Party Type",
			description: __("Only affects PDC rows - Recurring Commitment rows have no party."),
			on_change: () => frappe.query_report.set_filter_value("party", ""),
		},
		{
			fieldname: "party",
			label: __("Party"),
			fieldtype: "Dynamic Link",
			options: "party_type",
		},
		{
			fieldname: "include_overdue",
			label: __("Include Overdue PDCs"),
			fieldtype: "Check",
			default: 1,
			description: __("On: also show Pending cheques dated before From Date. Off: strictly bound to cheques dated within From/To Date."),
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		if (column.fieldname === "source" && data.source === "PDC") {
			value = `<span style="color:var(--blue-600);font-weight:600">${value}</span>`;
		}
		if (column.fieldname === "direction" && data.direction) {
			const color = data.direction === "In" ? "var(--green-600)" : "var(--red-600)";
			value = `<span style="color:${color};font-weight:600">${value}</span>`;
		}
		if (column.fieldname === "remarks" && data.remarks === "Overdue") {
			value = `<span style="color:var(--orange-600)">${value}</span>`;
		}

		return value;
	},
};
