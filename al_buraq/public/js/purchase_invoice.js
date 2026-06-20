frappe.ui.form.on("Purchase Invoice", {
	refresh: function (frm) {
		if (frm.doc.supplier) {
			frm.add_custom_button(__("Purchase History"), function () {
				_ab_show_purchase_history(frm.doc.supplier);
			}, __("View"));
		}
	},
});

function _ab_show_purchase_history(supplier) {
	frappe.call({
		method: "al_buraq.api.history.get_purchase_history",
		args: { supplier: supplier, limit: 20 },
		callback: function (r) {
			const invoices = r.message || [];
			if (!invoices.length) {
				frappe.msgprint(__("No purchase history found for {0}", [supplier]));
				return;
			}
			_ab_render_purchase_history_dialog(
				__("Purchase History — {0}", [supplier]),
				invoices
			);
		},
	});
}

function _ab_render_purchase_history_dialog(title, invoices) {
	let html = `
		<style>
			.ab-hist-table { width:100%; border-collapse:collapse; font-size:13px; }
			.ab-hist-table th { background:#f4f6f9; padding:8px 10px; text-align:left;
				border-bottom:2px solid #e0e6ed; font-weight:600; color:#5a6c7d; }
			.ab-hist-table td { padding:7px 10px; border-bottom:1px solid #f0f3f7; vertical-align:top; }
			.ab-hist-link { font-weight:700; color:#2563eb; cursor:pointer; }
			.ab-hist-link:hover { text-decoration:underline; }
			.ab-hist-items { font-size:12px; color:#5a6c7d; margin-top:3px; }
			.ab-hist-item-row { padding:1px 0; }
			.ab-status-paid { color:#059669; font-weight:600; }
			.ab-status-unpaid { color:#dc2626; font-weight:600; }
			.ab-status-partial { color:#d97706; font-weight:600; }
		</style>
		<table class="ab-hist-table">
			<thead>
				<tr>
					<th>Invoice</th>
					<th>Date</th>
					<th>Items</th>
					<th style="text-align:right">Total</th>
					<th style="text-align:right">Outstanding</th>
					<th>Status</th>
				</tr>
			</thead>
			<tbody>`;

	invoices.forEach(function (inv) {
		const status_class =
			inv.status === "Paid" ? "ab-status-paid" :
			inv.status === "Unpaid" ? "ab-status-unpaid" : "ab-status-partial";

		const items_html = (inv.items || []).map(function (it) {
			return `<div class="ab-hist-item-row">
				${frappe.utils.escape_html(it.item_code)} — ${frappe.utils.escape_html(it.item_name)}
				&nbsp;×&nbsp;${frappe.utils.fmt_money(it.qty, 0)} ${frappe.utils.escape_html(it.uom || "")}
				@ ${frappe.utils.fmt_money(it.rate)}
			</div>`;
		}).join("");

		html += `<tr>
			<td><span class="ab-hist-link" data-name="${frappe.utils.escape_html(inv.name)}">${frappe.utils.escape_html(inv.name)}</span></td>
			<td>${frappe.datetime.str_to_user(inv.posting_date)}</td>
			<td><div class="ab-hist-items">${items_html}</div></td>
			<td style="text-align:right">${frappe.utils.fmt_money(inv.grand_total)}</td>
			<td style="text-align:right">${frappe.utils.fmt_money(inv.outstanding_amount)}</td>
			<td><span class="${status_class}">${frappe.utils.escape_html(inv.status)}</span></td>
		</tr>`;
	});

	html += "</tbody></table>";

	const d = new frappe.ui.Dialog({ title: title, size: "extra-large" });
	d.$body.html(html);
	d.$body.on("click", ".ab-hist-link", function () {
		frappe.set_route("Form", "Purchase Invoice", $(this).data("name"));
	});
	d.show();
}
