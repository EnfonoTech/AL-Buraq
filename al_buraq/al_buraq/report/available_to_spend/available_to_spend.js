// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

frappe.query_reports["Available to Spend"] = {
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
			fieldname: "from_fiscal_year",
			label: __("From Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			reqd: 1,
		},
		{
			fieldname: "to_fiscal_year",
			label: __("To Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			reqd: 1,
		},
		{
			fieldname: "period",
			label: __("Period"),
			fieldtype: "Select",
			options: [
				{ value: "Monthly", label: __("Monthly") },
				{ value: "Quarterly", label: __("Quarterly") },
				{ value: "Half-Yearly", label: __("Half-Yearly") },
				{ value: "Yearly", label: __("Yearly") },
			],
			default: "Quarterly",
			reqd: 1,
		},
		{
			fieldname: "budget_against",
			label: __("Budget Against"),
			fieldtype: "Select",
			options: ["Cost Center", "Project"],
			default: "Cost Center",
			reqd: 1,
			on_change: function () {
				frappe.query_report.set_filter_value("budget_against_filter", []);
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "budget_against_filter",
			label: __("Dimension Filter"),
			fieldtype: "MultiSelectList",
			options: "budget_against",
			get_data: function (txt) {
				let budget_against = frappe.query_report.get_filter_value("budget_against");
				if (!budget_against) return;
				return frappe.db.get_link_options(budget_against, txt, {
					company: frappe.query_report.get_filter_value("company"),
				});
			},
		},
		{
			fieldname: "account",
			label: __("Account"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Account", txt, {
					company: frappe.query_report.get_filter_value("company"),
				});
			},
		},
		{
			fieldname: "commitment_basis",
			label: __("Commitment Basis"),
			fieldtype: "Select",
			options: ["Expected Date", "Transaction Date"],
			default: "Expected Date",
		},
		{
			fieldname: "show_cumulative",
			label: __("Show Cumulative Amount"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "hide_zero_rows",
			label: __("Hide Zero Rows"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "rollup_to_dimension",
			label: __("Rollup to Cost Center / Project (hide Account detail)"),
			fieldtype: "Check",
			default: 0,
			description: __("One row per Cost Center/Project, sorted by Utilisation % — use this to see who is approaching or exceeding budget at a glance."),
		},
		{
			fieldname: "only_at_risk",
			label: __("Only At Risk (Near Limit / Over Budget / Unbudgeted Spend)"),
			fieldtype: "Check",
			default: 0,
			description: __("Requires Rollup to Cost Center / Project — hides rows with Status 'OK' or 'No Budget'."),
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname.includes("available") && data[column.fieldname] < 0) {
			value = "<span style='color:var(--red-500)'>" + value + "</span>";
		} else if (column.fieldname === "utilisation_percent") {
			if (data.utilisation_percent >= 100) {
				value = "<span style='color:var(--red-500);font-weight:bold'>" + value + "</span>";
			} else if (data.utilisation_percent >= 90) {
				value = "<span style='color:var(--orange-500)'>" + value + "</span>";
			}
		} else if (column.fieldname === "status") {
			if (data.status === __("Over Budget") || data.status === __("Unbudgeted Spend")) {
				value = "<span style='color:var(--red-500);font-weight:bold'>" + value + "</span>";
			} else if (data.status === __("Near Limit")) {
				value = "<span style='color:var(--orange-500);font-weight:bold'>" + value + "</span>";
			}
		}

		if (data.account && (column.fieldname === "total_actual" || column.fieldname === "total_committed")) {
			value =
				"<a href='#' onclick=\"return al_buraq_drilldown('" +
				column.fieldname +
				"', '" +
				frappe.utils.escape_html(data.dimension) +
				"', '" +
				frappe.utils.escape_html(data.account) +
				"')\">" +
				value +
				"</a>";
		}

		return value;
	},
};

// Drilldown: open the GL Entries (Actual) or the Committed Amount report
// (Committed) behind a Total Actual / Total Committed cell, scoped to the
// same Cost Center/Project, Account and Fiscal Year range as this report.
window.al_buraq_drilldown = function (kind, dimension, account) {
	const report = frappe.query_report;
	const budget_against = report.get_filter_value("budget_against");
	const company = report.get_filter_value("company");
	const from_fiscal_year = report.get_filter_value("from_fiscal_year");
	const to_fiscal_year = report.get_filter_value("to_fiscal_year");
	const dimension_field = budget_against === "Project" ? "project" : "cost_center";

	if (kind === "total_committed") {
		frappe.route_options = {
			company: company,
			budget_against: budget_against,
			budget_against_filter: [dimension],
			account: [account],
			fiscal_year: to_fiscal_year,
			commitment_basis: report.get_filter_value("commitment_basis") || "Expected Date",
			show_details: 1,
		};
		frappe.set_route("query-report", "Committed Amount");
		return false;
	}

	Promise.all([
		frappe.db.get_value("Fiscal Year", from_fiscal_year, "year_start_date"),
		frappe.db.get_value("Fiscal Year", to_fiscal_year, "year_end_date"),
	]).then(([start, end]) => {
		const route_filters = {
			company: company,
			account: account,
			posting_date: ["between", [start.message.year_start_date, end.message.year_end_date]],
			is_cancelled: 0,
			docstatus: 1,
		};
		route_filters[dimension_field] = dimension;
		frappe.route_options = route_filters;
		frappe.set_route("List", "GL Entry", "list");
	});
	return false;
};
