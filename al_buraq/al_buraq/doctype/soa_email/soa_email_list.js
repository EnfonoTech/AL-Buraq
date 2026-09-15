// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

frappe.listview_settings["SOA Email"] = {
	onload: function (listview) {
		listview.page.add_action_item(__("Send SOA Emails"), () => {
			const docnames = listview.get_checked_items(true);

			if (!docnames.length) {
				frappe.msgprint(__("Please select at least one SOA Email to send"));
				return;
			}

			frappe.confirm(__("Send SOA email for {0} selected record(s)?", [docnames.length]), () => {
				frappe.call({
					method: "al_buraq.al_buraq.doctype.soa_email.soa_email.send_bulk_emails",
					args: {
						docnames: docnames,
					},
					freeze: true,
					freeze_message: __("Sending SOA emails..."),
					callback: function (r) {
						if (!r.message) return;

						const { sent, failed } = r.message;
						let summary = __("{0} email(s) sent successfully.", [sent.length]);

						if (failed.length) {
							summary += "<br>" + __("{0} failed:", [failed.length]);
							summary +=
								"<ul>" +
								failed.map((f) => `<li>${frappe.utils.escape_html(f.docname)}</li>`).join("") +
								"</ul>";
						}

						frappe.msgprint({
							title: __("Bulk SOA Email Result"),
							message: summary,
							indicator: failed.length ? "orange" : "green",
						});

						listview.refresh();
					},
				});
			});
		});
	},
};
