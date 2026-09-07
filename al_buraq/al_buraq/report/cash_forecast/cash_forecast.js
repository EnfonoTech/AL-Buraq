// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

frappe.query_reports["Cash Forecast"] = {
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
			default: frappe.datetime.add_days(frappe.datetime.get_today(), 90),
			reqd: 1,
		},
		{
			fieldname: "bucket",
			label: __("Bucket"),
			fieldtype: "Select",
			options: ["Weekly", "Monthly", "Quarterly"],
			default: "Monthly",
			reqd: 1,
			description: __("Weekly with the default 90-day window ≈ a rolling 13-week cash view."),
		},
		{
			fieldname: "include_overdue",
			label: __("Include Overdue"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "include_opening_cash",
			label: __("Include Opening Cash Balance"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "include_sales_orders",
			label: __("Include Unbilled Sales Orders"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "include_purchase_orders",
			label: __("Include Unbilled Purchase Orders"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "party_type",
			label: __("Party Type"),
			fieldtype: "Select",
			options: ["", "Customer", "Supplier"],
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
			fieldname: "classification",
			label: __("Classification"),
			fieldtype: "Select",
			options: ["", "Operating", "Investing", "Financing", "VAT/ZATCA Settlement"],
			description: __("Isolate one classification — e.g. VAT/ZATCA Settlement for KSA cash timing. The VAT/ZATCA Net column in summary mode always shows regardless of this filter."),
		},
		{
			fieldname: "include_recurring",
			label: __("Include Recurring Commitments"),
			fieldtype: "Check",
			default: 1,
			description: __("Payroll, rent, loan EMI, VAT/ZATCA settlements and other fixed commitments maintained under Recurring Cash Commitment."),
		},
		{
			fieldname: "apply_scenario",
			label: __("Apply What-If Scenario"),
			fieldtype: "Link",
			options: "Budget Scenario",
			description: __("Optional — applies that Scenario's 'Delay in Days' lines to shift matching due dates for this run only. Calculation-only: nothing is written back."),
			get_query: function () {
				return { filters: { company: frappe.query_report.get_filter_value("company"), budget_against: "Cost Center" } };
			},
		},
		{
			fieldname: "show_details",
			label: __("Show Details"),
			fieldtype: "Check",
			default: 0,
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname === "cumulative_cash" && data.cumulative_cash < 0) {
			value = "<span style='color:var(--red-500)'>" + value + "</span>";
		}
		if (column.fieldname === "period" && data.period === __("Overdue")) {
			value = "<span style='color:var(--red-500);font-weight:bold'>" + value + "</span>";
		}
		if (column.fieldname === "confidence" && data.confidence === __("Tentative")) {
			value = "<span style='color:var(--orange-500)'>" + value + "</span>";
		}

		return value;
	},
	onload: function (report) {
		if (!frappe.perm.has_perm("Cash Forecast Snapshot", 0, "create")) {
			return;
		}
		report.page.add_inner_button(__("Take Snapshot"), function () {
			if (frappe.query_report.get_filter_value("show_details")) {
				frappe.msgprint(__("Turn off Show Details first — Take Snapshot freezes the summary buckets currently shown."));
				return;
			}
			frappe.confirm(
				__("This saves the summary buckets currently shown as Cash Forecast Snapshot records, for later comparison against actual cash movement once each period has closed. Continue?"),
				function () {
					frappe.call({
						method: "al_buraq.api.cash_forecast_tools.save_cash_forecast_snapshot",
						args: { filters: frappe.query_report.get_filter_values() },
						freeze: true,
						freeze_message: __("Saving snapshot..."),
						callback: function (r) {
							if (!r.message) return;
							frappe.show_alert({
								message: __("Saved {0} period snapshot(s)", [(r.message.created || []).length]),
								indicator: "green",
							});
						},
					});
				}
			);
		});
	},
};
