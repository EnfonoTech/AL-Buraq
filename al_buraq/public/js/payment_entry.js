frappe.ui.form.on('Payment Entry', {
	mode_of_payment: function(frm) {
		set_pdc_account(frm);
	},
	payment_type: function(frm) {
		set_pdc_account(frm);
	},
	company: function(frm) {
		set_pdc_account(frm);
	},
	refresh: function(frm) {
		frm.set_query('custom_clearing_voucher_no', function() {
			return {
				query: 'al_buraq.api.pdc.get_pdc_clearing_vouchers',
				filters: {
					mode_of_payment: frm.doc.mode_of_payment,
					company: frm.doc.company,
					payment_type: frm.doc.payment_type,
				},
			};
		});
	}
});

function set_pdc_account(frm) {
	// Only the single "PDC" mode needs direction-based account routing.
	// "PDC Received" / "PDC Issued" already resolve via the standard
	// one-account-per-mode Frappe behaviour.
	if (frm.doc.mode_of_payment !== 'PDC' || !frm.doc.company) return;

	frappe.call({
		method: 'al_buraq.api.pdc.get_target_account',
		args: {
			mode_of_payment: frm.doc.mode_of_payment,
			company: frm.doc.company,
			payment_type: frm.doc.payment_type,
		},
		callback: function(r) {
			if (!r.message) return;
			if (frm.doc.payment_type === 'Receive') {
				frm.set_value('paid_to', r.message);
			} else if (frm.doc.payment_type === 'Pay') {
				frm.set_value('paid_from', r.message);
			}
		},
	});
}
