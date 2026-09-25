// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

frappe.query_reports["PDC Allocation"] = {
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
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.month_end(), 2),
			reqd: 1,
		},
		{
			fieldname: "bank_gl_account",
			label: __("Bank GL Account"),
			fieldtype: "Link",
			options: "Account",
			description: __("Only affects In Bank rows - Pending cheques have no bank assigned yet."),
			get_query: () => ({
				filters: {
					company: frappe.query_report.get_filter_value("company"),
					account_type: "Bank",
					is_group: 0,
				},
			}),
		},
		{
			fieldname: "pdc_type",
			label: __("PDC Type"),
			fieldtype: "Select",
			options: "\nReceivable\nPayable",
		},
		{
			fieldname: "pdc_status",
			label: __("PDC Status"),
			fieldtype: "Select",
			options: "\nPending\nIn Bank",
		},
		{
			fieldname: "party_type",
			label: __("Party Type"),
			fieldtype: "Link",
			options: "Party Type",
			on_change: () => frappe.query_report.set_filter_value("party", ""),
		},
		{
			fieldname: "party",
			label: __("Party"),
			fieldtype: "Dynamic Link",
			options: "party_type",
		},
		{
			fieldname: "opening_balance",
			label: __("Opening Balance (override)"),
			fieldtype: "Currency",
			description: __("Leave blank to use the actual Bank GL balance as of the day before From Date."),
		},
		{
			fieldname: "include_overdue",
			label: __("Include Overdue Uncleared"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "include_draft",
			label: __("Include Draft Entries"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "show_month_totals",
			label: __("Show Month Totals"),
			fieldtype: "Check",
			default: 1,
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		if (column.fieldname === "status" && data.status) {
			const color = data.status === "Shortfall" ? "var(--red-600)" : "var(--green-600)";
			value = `<span style="color:${color};font-weight:600">${value}</span>`;
		}
		if (column.fieldname === "pdc_type" && data.pdc_type) {
			const color = data.pdc_type === "Receivable" ? "var(--green-600)" : "var(--red-600)";
			value = `<span style="color:${color};font-weight:600">${value}</span>`;
		}
		if (column.fieldname === "running_balance" && data.running_balance < 0) {
			value = `<span style="color:var(--red-600)">${value}</span>`;
		}
		if (column.fieldname === "cheque_status" && data.cheque_status === "In Bank") {
			value = `<span style="color:var(--orange-600)">${value}</span>`;
		}
		if (column.fieldname === "remarks" && data.remarks && data.remarks.includes("Overdue")) {
			value = `<span style="color:var(--orange-600)">${value}</span>`;
		}
		if (data.row_type === "total" || data.row_type === "opening") {
			value = `<b>${value}</b>`;
		}
		return value;
	},
};
