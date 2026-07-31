frappe.query_reports["PDC Register"] = {
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
			label: __("Cheque Date From"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("Cheque Date To"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
			reqd: 1,
		},
		{
			fieldname: "direction",
			label: __("Direction"),
			fieldtype: "Select",
			options: "\nReceivable\nPayable",
		},
		{
			fieldname: "pdc_status",
			label: __("PDC Status"),
			fieldtype: "Select",
			options: "\nPending\nIn Bank\nCleared",
		},
		{
			fieldname: "payment_type",
			label: __("Payment Type"),
			fieldtype: "Select",
			options: "\nReceive\nPay\nInternal Transfer",
		},
		{
			fieldname: "bank_gl_account",
			label: __("Bank GL Account"),
			fieldtype: "Link",
			options: "Account",
		},
	],
};
