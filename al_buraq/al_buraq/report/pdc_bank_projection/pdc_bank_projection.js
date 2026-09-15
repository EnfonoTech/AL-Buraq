frappe.query_reports["PDC Bank Projection"] = {
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
		},
		{
			fieldname: "pdc_status",
			label: __("PDC Status"),
			fieldtype: "Select",
			options: "\nPending\nIn Bank",
		},
		{
			fieldname: "bank_gl_account",
			label: __("Bank GL Account"),
			fieldtype: "Link",
			options: "Account",
			description: __("Only affects In Bank rows - Pending cheques have no bank assigned yet."),
		},
	],
};
