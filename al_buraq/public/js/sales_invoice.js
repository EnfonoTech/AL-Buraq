console.log("[al_buraq] sales_invoice.js loaded");

frappe.ui.form.on("Sales Invoice", {
	refresh: function (frm) {
		console.log("[al_buraq] refresh — payment_mode:", frm.doc.custom_payment_mode, "docstatus:", frm.doc.docstatus, "grand_total:", frm.doc.grand_total, "name:", frm.doc.name);
	},

	before_submit: function (frm) {
		console.log("[al_buraq] before_submit fired — payment_mode:", frm.doc.custom_payment_mode, "grand_total:", frm.doc.grand_total, "ab_submitting:", frappe.flags.ab_submitting);
		if (frappe.flags.ab_submitting) return;
		if (frm.doc.custom_payment_mode !== "Cash") return;
		if (flt(frm.doc.grand_total) <= 0) return;

		// Block Frappe's submit flow; our popup will re-trigger it.
		frappe.validated = false;
		_ab_open(frm);
	},
});

// ── Fetch modes then open dialog ──────────────────────────────────────────────

function _ab_open(frm) {
	if (frappe.flags.ab_popup_open) return;
	frappe.flags.ab_popup_open = true;

	frappe.call({
		method: "al_buraq.api.payment.get_payment_modes",
		args: { company: frm.doc.company },
		callback: function (r) {
			var modes = r.message || [];
			if (!modes.length) {
				frappe.flags.ab_popup_open = false;
				frappe.msgprint(__("No payment modes configured for this company."));
				return;
			}
			_ab_dialog(frm, modes);
		},
		error: function () {
			frappe.flags.ab_popup_open = false;
			frappe.msgprint(__("Could not load payment modes. Please try again."));
		},
	});
}

// ── Payment dialog ────────────────────────────────────────────────────────────

function _ab_dialog(frm, modes) {
	var total = flt(frm.doc.rounded_total || frm.doc.grand_total || 0);
	var cur   = frm.doc.currency || "";
	var dlg;

	var fields = [
		{
			fieldname: "remaining",
			fieldtype: "Currency",
			label: __("Amount to Pay"),
			default: total,
			read_only: 1,
			options: cur,
		},
		{ fieldtype: "Section Break" },
	];

	modes.forEach(function (mode, i) {
		fields.push(
			{
				fieldname: "pay_" + i,
				fieldtype: "Currency",
				label: mode,
				default: 0,
				options: cur,
				onchange: function () { _ab_sync(dlg, modes, total); },
			},
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Button",
				fieldname: "fill_" + i,
				label: mode,
				click: function () {
					var v = dlg.get_values(true) || {};
					var others = modes.reduce(function (s, _, j) {
						return j === i ? s : s + (flt(v["pay_" + j]) || 0);
					}, 0);
					dlg.set_value("pay_" + i, flt(Math.max(0, total - others), 2));
					_ab_sync(dlg, modes, total);
				},
			},
			{ fieldtype: "Section Break" }
		);
	});

	dlg = new frappe.ui.Dialog({
		title: __("Enter Payment Amounts"),
		fields: fields,
		primary_action_label: __("Submit"),
		primary_action: function (vals) {
			_ab_submit(frm, dlg, modes, vals, total, cur);
		},
		secondary_action_label: __("Cancel"),
		secondary_action: function () {
			dlg.hide();
		},
		onhide: function () {
			frappe.flags.ab_popup_open = false;
		},
	});

	dlg.show();
}

function _ab_sync(dlg, modes, total) {
	if (!dlg) return;
	var v = dlg.get_values(true) || {};
	var entered = modes.reduce(function (s, _, i) {
		return s + (flt(v["pay_" + i]) || 0);
	}, 0);
	dlg.set_value("remaining", flt(total - entered, 2));
}

// ── Validate amounts then submit ──────────────────────────────────────────────

function _ab_submit(frm, dlg, modes, vals, total, cur) {
	var entered = modes.reduce(function (s, _, i) {
		return s + (flt(vals["pay_" + i]) || 0);
	}, 0);

	if (entered > 0 && entered < total - 0.01) {
		frappe.msgprint({
			title: __("Incomplete"),
			message: __("{0} still to be allocated.", [format_currency(total - entered, cur)]),
			indicator: "red",
		});
		return;
	}
	if (entered - total > 0.5) {
		frappe.msgprint({
			title: __("Error"),
			message: __("Amount {0} exceeds invoice total {1}.", [
				format_currency(entered, cur), format_currency(total, cur),
			]),
			indicator: "red",
		});
		return;
	}

	var payload = [];
	modes.forEach(function (mode, i) {
		var amt = flt(vals["pay_" + i]) || 0;
		if (amt > 0) payload.push({ mode_of_payment: mode, amount: amt });
	});

	dlg.hide();
	frappe.flags.ab_popup_open = false;
	frappe.flags.ab_submitting = true;

	// frm.savesubmit() shows Frappe's confirm dialog then fires before_submit.
	// Calling frm.save("Submit") skips both — submit directly.
	frm.save("Submit").then(function () {
		frappe.flags.ab_submitting = false;

		if (frm.doc.docstatus !== 1) {
			frm.reload_doc();
			return;
		}
		if (!payload.length) {
			frm.reload_doc();
			return;
		}

		frappe.call({
			method: "al_buraq.api.payment.create_payment_entries",
			args: {
				sales_invoice: frm.doc.name,
				payments: JSON.stringify(payload),
			},
			freeze: true,
			freeze_message: __("Creating Payment Entries…"),
			callback: function (res) {
				var n = ((res && res.message) || []).length;
				if (n) {
					frappe.show_alert({
						message: __("{0} Payment {1} created", [n, n === 1 ? "Entry" : "Entries"]),
						indicator: "green",
					}, 5);
				}
				frm.reload_doc();
			},
			error: function () {
				frappe.msgprint({
					title: __("Note"),
					message: __("Invoice submitted. Please create payment entries manually."),
					indicator: "orange",
				});
				frm.reload_doc();
			},
		});
	}).catch(function () {
		frappe.flags.ab_submitting = false;
		frm.reload_doc();
	});
}

