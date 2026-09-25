// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

frappe.query_reports["Cheque Allocation Forecast"] = {
	tree: false,
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
			fieldname: "bank_account",
			label: __("Bank Account"),
			fieldtype: "Link",
			options: "Account",
			description: __("Chart of Accounts entry (type Bank). Leave blank to sum all of this Company's bank-type accounts (Cheques in Hand accounts are excluded automatically)."),
			get_query: () => ({
				filters: {
					company: frappe.query_report.get_filter_value("company"),
					account_type: "Bank",
					is_group: 0,
				},
			}),
		},
		{
			fieldname: "opening_balance_override",
			label: __("Opening Balance Override"),
			fieldtype: "Currency",
			description: __("Leave blank to use the actual GL balance of the Bank Account(s) as of the day before From Date."),
		},
		{
			fieldname: "cutoff_days",
			label: __("Window Cut-off Days"),
			fieldtype: "Data",
			default: "5,15,28",
			description: __("Comma-separated days of month (e.g. 5,15,28). Every transaction falls into the next cut-off on/after its date; the last cut-off of a month covers everything up to month end."),
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		if (data.is_total) {
			value = `<b>${value}</b>`;
		}

		if (
			(data.row_type === "opening_fund" || data.row_type === "fund" || data.row_type === "closing_fund") &&
			column.fieldname === "recv_amount"
		) {
			const color = flt(data.recv_amount) < 0 ? "var(--red-600)" : "var(--green-600)";
			value = `<span style="color:${color}">${value}</span>`;
		}

		return value;
	},
};
