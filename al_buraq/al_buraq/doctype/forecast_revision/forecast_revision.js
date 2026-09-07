// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("Forecast Revision", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}
		frm.add_custom_button(__("Get Accounts from Budget"), () => {
			const dimension = frm.doc.budget_against === "Cost Center" ? frm.doc.cost_center : frm.doc.project;
			if (!frm.doc.company || !frm.doc.fiscal_year || !dimension) {
				frappe.msgprint(__("Set Company, Fiscal Year and {0} first", [frm.doc.budget_against]));
				return;
			}
			frappe.call({
				method: "al_buraq.api.forecast_tools.get_budget_accounts",
				args: {
					company: frm.doc.company,
					fiscal_year: frm.doc.fiscal_year,
					budget_against: frm.doc.budget_against,
					dimension: dimension,
				},
				callback: (r) => {
					if (!r.message || !r.message.length) {
						frappe.msgprint(__("No Budget found for this Company, Fiscal Year and {0}", [frm.doc.budget_against]));
						return;
					}
					r.message.forEach((row) => {
						let child = frm.add_child("forecast_lines");
						child.account = row.account;
						child.month = row.month;
						child.forecast_amount = row.forecast_amount;
					});
					frm.refresh_field("forecast_lines");
					frappe.show_alert({ message: __("{0} rows added from Budget", [r.message.length]), indicator: "green" });
				},
			});
		});
	},
});
