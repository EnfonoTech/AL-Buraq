// Last Purchase Rate for al_buraq
// Adds a "Last Purchase Rate" button to the items grid toolbar on all purchase
// and sales-side workflow doctypes. Opens a dialog showing full purchase history
// for a selected item, filterable by column.

frappe.provide("al_buraq");

al_buraq.add_last_purchase_rate_button = function (frm) {
	if (!frm.fields_dict.items || !frm.fields_dict.items.grid) return;

	const grid = frm.fields_dict.items.grid;

	if (!grid.wrapper.data("al_buraq_lpr_click_bound")) {
		const remember = function (e) {
			const $body = grid.wrapper.find(".grid-body");
			if (!$body.length || !$body[0].contains(e.target)) return;
			const $row = $(e.target).closest(".grid-row");
			if (!$row.length) return;
			const grid_row = $row.data("grid_row");
			if (grid_row && grid_row.doc && grid_row.doc.item_code) {
				frm._al_buraq_lpr_focused_item = grid_row.doc.item_code;
			}
		};
		grid.wrapper[0].addEventListener("click", remember, true);
		grid.wrapper[0].addEventListener("focusin", remember, true);
		grid.wrapper[0].addEventListener("focusout", remember, true);
		grid.wrapper.data("al_buraq_lpr_click_bound", true);
	}

	let $toolbar = grid.wrapper.find(".grid-buttons");
	if (!$toolbar.length) $toolbar = grid.wrapper.find(".grid-footer .grid-buttons");
	if (!$toolbar.length) return;

	if ($toolbar.find("button:contains('Last Purchase Rate')").length > 0) return;

	let $target = $toolbar.find("button:contains('Add Multiple')").last();
	if (!$target.length) $target = $toolbar.find("button:contains('Add Row')").last();

	const btn = $(
		`<button type="button" class="btn btn-secondary btn-xs" style="margin-left: 10px;">${__(
			"Last Purchase Rate"
		)}</button>`
	);
	btn.on("click", function () {
		const default_item = al_buraq.get_default_item_for_lpr(frm);
		al_buraq.open_last_purchase_rate_dialog(frm, default_item);
	});

	if ($target.length > 0 && $target.parent().is($toolbar)) {
		btn.insertAfter($target);
	} else {
		$toolbar.append(btn);
	}
};

al_buraq.get_default_item_for_lpr = function (frm) {
	if (!frm || !frm.fields_dict.items || !frm.fields_dict.items.grid) return null;
	const items_grid = frm.fields_dict.items.grid;

	const open_row = frappe.ui.form.get_open_grid_form();
	if (open_row && open_row.grid === items_grid && open_row.doc && open_row.doc.item_code) {
		return open_row.doc.item_code;
	}
	if (frm._al_buraq_lpr_focused_item) {
		return frm._al_buraq_lpr_focused_item;
	}
	if (frm.doc.items && frm.doc.items.length) {
		const last = frm.doc.items[frm.doc.items.length - 1];
		if (last && last.item_code) return last.item_code;
	}
	return null;
};

al_buraq.open_last_purchase_rate_dialog = function (frm, default_item_code) {
	const company = frm.doc.company || frappe.defaults.get_default("company");

	const d = new frappe.ui.Dialog({
		title: __("Last Purchase Rate"),
		fields: [
			{
				fieldname: "item_code",
				label: __("Item Code"),
				fieldtype: "Link",
				options: "Item",
				default: default_item_code,
				get_query: function () {
					return {
						query: "erpnext.controllers.queries.item_query",
						filters: { is_purchase_item: 1, company: company },
					};
				},
			},
			{ fieldname: "results", fieldtype: "HTML" },
		],
		size: "extra-large",
		primary_action_label: __("Close"),
		primary_action: function () {
			d.hide();
		},
	});

	d._company = company;
	d.show();

	setTimeout(() => {
		if (d.fields_dict.item_code) {
			d.fields_dict.item_code.df.onchange = function () {
				const item_code = d.get_value("item_code");
				if (item_code) al_buraq.fetch_last_purchase_rate(item_code, company, d);
			};
			d.fields_dict.item_code.refresh();
		}
		if (default_item_code) {
			al_buraq.fetch_last_purchase_rate(default_item_code, company, d);
		}
	}, 200);
};

al_buraq.fetch_last_purchase_rate = function (item_code, company, dialog) {
	dialog.fields_dict.results.$wrapper.html(
		'<div class="text-muted">' + __("Loading…") + "</div>"
	);

	frappe.call({
		method: "al_buraq.api.last_purchase_rate.get_item_purchase_history",
		args: {
			item_code: item_code,
			company: dialog._company || null,
			limit: 20,
		},
		callback: function (r) {
			const rows = r.message || [];
			if (!rows.length) {
				dialog.fields_dict.results.$wrapper.html(
					'<div class="text-muted">' + __("No purchase history found for this item.") + "</div>"
				);
				return;
			}
			dialog.fields_dict.results.$wrapper.html(
				al_buraq.render_purchase_history_table(rows)
			);
			dialog.fields_dict.results.$wrapper
				.find("[data-doctype][data-name]")
				.on("click", function () {
					frappe.set_route("Form", this.getAttribute("data-doctype"), this.getAttribute("data-name"));
				});
			setTimeout(() => al_buraq.setupPurchaseTableFilters(dialog), 100);
		},
		error: function (err) {
			dialog.fields_dict.results.$wrapper.html(
				'<div class="text-danger">' +
					__("Error fetching data: {0}", [err.message || err]) +
					"</div>"
			);
		},
	});
};

al_buraq.render_purchase_history_table = function (rows) {
	var out = [
		'<div class="mt-3">',
		'<table class="table table-bordered table-sm" id="al-buraq-purchase-history-table">',
		"<thead>",
		"<tr>",
		"<th>" + __("Date") + "</th>",
		"<th>" + __("Purchase Invoice") + "</th>",
		"<th>" + __("Supplier") + "</th>",
		"<th>" + __("Item Code") + "</th>",
		"<th>" + __("Item Name") + "</th>",
		'<th class="text-right">' + __("Qty") + "</th>",
		'<th class="text-right">' + __("UOM") + "</th>",
		'<th class="text-right">' + __("Purchase Rate") + "</th>",
		'<th class="text-right">' + __("Amount") + "</th>",
		"</tr>",
		'<tr class="filter-row">',
		'<th><input type="text" class="form-control input-sm" placeholder="' + __("Filter Date") + '"></th>',
		'<th><input type="text" class="form-control input-sm" placeholder="' + __("Filter Invoice") + '"></th>',
		'<th><input type="text" class="form-control input-sm" placeholder="' + __("Filter Supplier") + '"></th>',
		'<th><input type="text" class="form-control input-sm" placeholder="' + __("Filter Item Code") + '"></th>',
		'<th><input type="text" class="form-control input-sm" placeholder="' + __("Filter Item Name") + '"></th>',
		'<th><input type="text" class="form-control input-sm" placeholder="' + __("Filter Qty") + '"></th>',
		'<th><input type="text" class="form-control input-sm" placeholder="' + __("Filter UOM") + '"></th>',
		'<th><input type="text" class="form-control input-sm" placeholder="' + __("Filter Rate") + '"></th>',
		'<th><input type="text" class="form-control input-sm" placeholder="' + __("Filter Amount") + '"></th>',
		"</tr>",
		"</thead>",
		"<tbody>",
	].join("");

	rows.forEach(function (r) {
		const posting_date = frappe.utils.escape_html(frappe.datetime.str_to_user(r.posting_date || ""));
		const purchase_invoice = frappe.utils.escape_html(r.purchase_invoice || "");
		const supplier = frappe.utils.escape_html(r.supplier_name || r.supplier || "");
		const item_code = frappe.utils.escape_html(r.item_code || "");
		const item_name = frappe.utils.escape_html(r.item_name || "");
		const qty = format_number(r.qty || 0, null, { precision: 2 });
		const uom = frappe.utils.escape_html(r.uom || "");
		const purchase_rate = format_currency(r.purchase_rate || 0, r.currency || "");
		const amount = format_currency(r.purchase_amount || 0, r.currency || "");

		out += [
			"<tr>",
			`<td>${posting_date}</td>`,
			`<td><a href="#" data-doctype="Purchase Invoice" data-name="${purchase_invoice}" class="text-primary">${purchase_invoice}</a></td>`,
			`<td>${supplier}</td>`,
			`<td>${item_code}</td>`,
			`<td>${item_name}</td>`,
			`<td class="text-right">${qty}</td>`,
			`<td class="text-right">${uom}</td>`,
			`<td class="text-right"><strong>${purchase_rate}</strong></td>`,
			`<td class="text-right">${amount}</td>`,
			"</tr>",
		].join("");
	});

	out += "</tbody></table></div>";
	return out;
};

al_buraq.setupPurchaseTableFilters = function (dialog) {
	const table = dialog.fields_dict.results.$wrapper.find("#al-buraq-purchase-history-table")[0];
	if (!table) return;

	const filterInputs = table.querySelectorAll(".filter-row input");
	filterInputs.forEach(function (input) {
		if (input._filterHandler) {
			input.removeEventListener("input", input._filterHandler);
			delete input._filterHandler;
		}
		input._filterHandler = function () {
			al_buraq.applyAllPurchaseFilters(dialog);
		};
		input.addEventListener("input", input._filterHandler);
	});
};

al_buraq.applyAllPurchaseFilters = function (dialog) {
	const table = dialog.fields_dict.results.$wrapper.find("#al-buraq-purchase-history-table")[0];
	if (!table) return;

	const rows = table.querySelectorAll("tbody tr");
	const filterInputs = table.querySelectorAll(".filter-row input");

	rows.forEach(function (row) {
		let shouldShow = true;
		filterInputs.forEach(function (input, j) {
			const val = input.value.toLowerCase().trim();
			if (!val) return;
			const cell = row.cells[j];
			if (cell && (cell.textContent || "").toLowerCase().indexOf(val) === -1) {
				shouldShow = false;
			}
		});
		row.style.display = shouldShow ? "" : "none";
	});
};

// All purchase-side doctypes + sales-side (as pricing reference)
const _al_buraq_lpr_doctypes = [
	// Purchase workflow
	"Request for Quotation",
	"Supplier Quotation",
	"Purchase Order",
	"Purchase Receipt",
	"Purchase Invoice",
	// Sales workflow — useful as a pricing reference
	"Quotation",
	"Sales Order",
	"Sales Invoice",
];

_al_buraq_lpr_doctypes.forEach(function (doctype) {
	frappe.ui.form.on(doctype, {
		refresh: function (frm) {
			let attempts = 0;
			const maxAttempts = 8;
			const tryAddButton = function () {
				attempts++;
				if (frm.fields_dict.items && frm.fields_dict.items.grid) {
					al_buraq.add_last_purchase_rate_button(frm);
					const $toolbar = frm.fields_dict.items.grid.wrapper.find(".grid-buttons");
					if ($toolbar.find("button:contains('Last Purchase Rate')").length > 0) return;
				}
				if (attempts < maxAttempts) setTimeout(tryAddButton, 400);
			};
			setTimeout(tryAddButton, 800);
		},
		items_add: function (frm) {
			setTimeout(function () {
				al_buraq.add_last_purchase_rate_button(frm);
			}, 800);
		},
	});
});
