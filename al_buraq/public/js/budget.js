frappe.ui.form.on("Budget", {
	refresh: function (frm) {
		frm.add_custom_button(__("Suggest Budget from History"), function () {
			frappe.route_options = {
				company: frm.doc.company,
				target_fiscal_year: frm.doc.fiscal_year,
				budget_against: frm.doc.budget_against || "Cost Center",
				budget_against_filter: frm.doc.budget_against === "Project" ? (frm.doc.project ? [frm.doc.project] : []) : frm.doc.cost_center ? [frm.doc.cost_center] : [],
			};
			frappe.set_route("query-report", "Budget Suggestion");
		});
	},
});
