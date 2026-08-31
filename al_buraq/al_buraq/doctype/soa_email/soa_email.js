// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("SOA Email", {
	party: function (frm) {
		if (frm.doc.party_type && frm.doc.party) {
			frappe.call({
				method: "frappe.client.get_value",
				args: {
					doctype: frm.doc.party_type,
					filters: { name: frm.doc.party },
					fieldname: "email_id",
				},
				callback: function (r) {
					if (r.message && r.message.email_id) {
						frm.set_value("email_to", r.message.email_id);
					}
				},
			});
		}
	},

	refresh: function (frm) {
		frm.set_query("print_format", "transactions", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			return {
				filters: {
					doc_type: row.reference_type,
				},
			};
		});

		frm.set_query("soa_print_format", function () {
			return {
				filters: {
					print_format_for: "Report",
					report: frm.doc.soa_report,
				},
			};
		});

		frm.add_custom_button(__("Get Transactions"), function () {
			if (!frm.doc.company || !frm.doc.party_type || !frm.doc.party || !frm.doc.from_date || !frm.doc.to_date) {
				frappe.msgprint(__("Please select Company, Party Type, Party, From Date and To Date"));
				return;
			}

			frappe.call({
				method: "al_buraq.al_buraq.doctype.soa_email.soa_email.get_transactions",
				args: {
					party_type: frm.doc.party_type,
					party: frm.doc.party,
					from_date: frm.doc.from_date,
					to_date: frm.doc.to_date,
					company: frm.doc.company,
				},
				callback: function (r) {
					if (r.message && r.message.length) {
						frm.clear_table("transactions");
						r.message.forEach(function (item) {
							let row = frm.add_child("transactions");
							row.reference_type = item.reference_type;
							row.reference_name = item.reference_name;
							row.parent_invoice = item.parent_invoice;
							row.include_in_email = item.include_in_email;
							row.print_format = item.print_format;
						});
						frm.refresh_field("transactions");
						frappe.msgprint(__("{0} rows found", [r.message.length]));
					} else {
						frappe.msgprint(__("No invoices found"));
					}
				},
			});
		});

		if (!frm.doc.__islocal) {
			frm.add_custom_button(__("Send Email"), function () {
				frappe.confirm(
					__("Are you sure you want to send this email to {0}?", [frm.doc.email_to]),
					function () {
						// send_email() reads this doc fresh from the database, so any
						// unsaved changes (e.g. Get Transactions rows, checkbox edits)
						// must be persisted first or they will silently be left out.
						const send = () => {
							frappe.call({
								method: "al_buraq.al_buraq.doctype.soa_email.soa_email.send_email",
								args: {
									docname: frm.doc.name,
								},
								freeze: true,
								freeze_message: __("Generating PDFs and sending email..."),
								callback: function (r) {
									if (r.message) {
										frappe.msgprint(r.message);
									}
								},
							});
						};

						if (frm.is_dirty()) {
							frm.save().then(send);
						} else {
							send();
						}
					}
				);
			});
		}
	},
});
