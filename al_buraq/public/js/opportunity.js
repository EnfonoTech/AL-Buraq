// Requirement 2.3.1: turn an enquiry into a Job.
frappe.ui.form.on("Opportunity", {
	refresh: function (frm) {
		if (frm.is_new() || ["Lost", "Closed"].includes(frm.doc.status)) return;

		frm.add_custom_button(__("Job"), function () {
			frappe.call({
				method: "al_buraq.api.job.make_job_from_opportunity",
				args: { opportunity: frm.doc.name },
				freeze: true,
				callback: function (r) {
					if (!r.message) return;
					if (!r.message.created) {
						frappe.show_alert({ message: __("This enquiry already has job {0}", [r.message.name]), indicator: "orange" });
					}
					frappe.set_route("Form", "Job Record", r.message.name);
				},
			});
		}, __("Create"));
	},
});
