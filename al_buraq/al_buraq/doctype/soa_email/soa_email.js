// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("SOA Email", {
	party_type: function (frm) {
		// Dynamic Link fields resolve their target doctype from another
		// field's value (see options: "invoice_reference_doctype" in the
		// json) - keep that hidden field in sync with party_type so the
		// Invoice Reference field always searches the right doctype.
		frm.set_value(
			"invoice_reference_doctype",
			frm.doc.party_type === "Customer" ? "Sales Invoice" : frm.doc.party_type === "Supplier" ? "Purchase Invoice" : ""
		);
		frm.set_value("invoice_reference", "");
	},

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

	email_template: function (frm) {
		if (!frm.doc.email_template) return;
		// Load the template's rendered subject/message straight into the
		// Subject/Message fields so the user can review or edit it before
		// sending - these two fields, not the template link, are what
		// actually gets sent (see get_email_subject_and_message()).
		frappe.call({
			method: "al_buraq.al_buraq.doctype.soa_email.soa_email.fetch_email_template_content",
			args: {
				doc: frm.doc,
			},
			callback: function (r) {
				if (r.message) {
					frm.set_value("subject", r.message.subject);
					frm.set_value("message", r.message.message);
				}
			},
		});
	},

	refresh: function (frm) {
		// Documents saved before the Invoice Reference field existed never
		// fired the party_type change handler above, so their hidden
		// invoice_reference_doctype stays blank and the Dynamic Link has no
		// doctype to search - keep it in sync here too, on every load.
		const expected_ref_doctype =
			frm.doc.party_type === "Customer" ? "Sales Invoice" : frm.doc.party_type === "Supplier" ? "Purchase Invoice" : "";
		if (frm.doc.invoice_reference_doctype !== expected_ref_doctype) {
			frm.set_value("invoice_reference_doctype", expected_ref_doctype);
		}

		frm.set_query("print_format", "transactions", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			// Print Format's own read permission is restricted to System
			// Manager on this site, so the default Link-field search returns
			// nothing for any other role even though matching records exist.
			// Route through a whitelisted server method that deliberately
			// bypasses that restriction instead.
			return {
				query: "al_buraq.al_buraq.doctype.soa_email.soa_email.get_print_formats_for_doctype",
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

		frm.set_query("invoice_reference", function () {
			const party_field = frm.doc.party_type === "Customer" ? "customer" : "supplier";
			const filters = { docstatus: 1 };
			if (frm.doc.party) filters[party_field] = frm.doc.party;
			if (frm.doc.company) filters.company = frm.doc.company;
			return { filters };
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
					invoice_reference: frm.doc.invoice_reference,
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
						setup_include_in_email_header_checkbox(frm);
						frappe.msgprint(__("{0} rows found", [r.message.length]));
					} else {
						frappe.msgprint(__("No invoices found"));
					}
				},
			});
		});

		setup_include_in_email_header_checkbox(frm);

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

function setup_include_in_email_header_checkbox(frm) {
	// Adds a "check/uncheck all" checkbox directly into the "Include in
	// Email" column's own header cell in the Transactions grid, instead of
	// a separate toolbar button - Frappe's Grid has no built-in option for
	// this, so it is injected into the rendered header row after the fact.
	//
	// Grid.refresh() unconditionally calls make_head(), which tears down
	// and rebuilds the whole heading row - this happens very often
	// (whenever the grid re-renders, not just on our own calls), silently
	// wiping out anything injected with a one-off setTimeout. So make_head
	// itself is wrapped once to always re-inject right after it rebuilds
	// the header, instead of relying on a single delayed injection.
	const grid_field = frm.fields_dict.transactions;
	if (!grid_field || !grid_field.grid) return;
	const grid = grid_field.grid;

	function inject() {
		const $header = grid.wrapper.find(
			'.grid-heading-row .grid-row:not(.filter-row) [data-fieldname="include_in_email"]'
		);
		if (!$header.length || $header.find(".include-in-email-toggle-all").length) return;

		// The label text ("Include in Email") already overflows this narrow
		// column and is clipped with an ellipsis by its own .static-area -
		// simply appending the checkbox after it left it stuck on a hidden
		// second line. Making the header cell a flex row (label shrinks with
		// its own ellipsis, checkbox stays a fixed size) keeps both visible
		// on one line instead.
		$header.css({ display: "flex", "align-items": "center", gap: "4px" });
		$header.find(".static-area").css({ flex: "1 1 auto", "min-width": "0" });

		const $checkbox = $(
			'<input type="checkbox" class="include-in-email-toggle-all" title="' +
				__("Check/uncheck all") +
				'" style="flex: 0 0 auto; margin: 0;">'
		);
		// Every click saves via frm.refresh_field(), which makes the grid
		// rebuild the whole header row from scratch (see make_head patch
		// below) - so this checkbox is a brand new <input> each time and
		// would otherwise always come back unchecked, making it look like
		// only "check all" ever works. Seed its checked state from the
		// actual data instead, so a completed "check all" shows as checked
		// and the next click correctly unchecks everything.
		const rows = frm.doc.transactions || [];
		const all_checked = rows.length > 0 && rows.every((row) => cint(row.include_in_email) === 1);
		$checkbox.prop("checked", all_checked);
		$header.append($checkbox);

		$checkbox.on("click", function (e) {
			e.stopPropagation();
			const checked = $(this).is(":checked") ? 1 : 0;
			(frm.doc.transactions || []).forEach(function (row) {
				frappe.model.set_value(row.doctype, row.name, "include_in_email", checked);
			});
			frm.refresh_field("transactions");
		});
	}

	if (!grid.__include_in_email_header_patched) {
		grid.__include_in_email_header_patched = true;
		const original_make_head = grid.make_head.bind(grid);
		grid.make_head = function () {
			original_make_head();
			inject();
		};
	}

	inject();
}
