// Stock Availability dialog button for al_buraq
// Adds a "Stock Availability" button to the items grid toolbar on all Sales and
// Purchase workflow doctypes. Clicking it opens a dialog showing per-warehouse
// stock for a selected item.

frappe.provide("al_buraq");

al_buraq.add_stock_availability_button = function (frm) {
	if (!frm.fields_dict.items || !frm.fields_dict.items.grid) return;

	const grid = frm.fields_dict.items.grid;

	// Track last clicked / focused row so the dialog can default to it.
	if (!grid.wrapper.data("al_buraq_stock_avail_click_bound")) {
		const remember = function (e) {
			const $body = grid.wrapper.find(".grid-body");
			if (!$body.length || !$body[0].contains(e.target)) return;
			const $row = $(e.target).closest(".grid-row");
			if (!$row.length) return;
			const grid_row = $row.data("grid_row");
			if (grid_row && grid_row.doc) {
				frm._al_buraq_stock_avail_row_cdt = grid_row.doc.doctype;
				frm._al_buraq_stock_avail_row_cdn = grid_row.doc.name;
			}
		};
		grid.wrapper[0].addEventListener("click", remember, true);
		grid.wrapper[0].addEventListener("focusin", remember, true);
		grid.wrapper.data("al_buraq_stock_avail_click_bound", true);
	}

	let $toolbar = grid.wrapper.find(".grid-buttons");
	if (!$toolbar.length) $toolbar = grid.wrapper.find(".grid-footer .grid-buttons");
	if (!$toolbar.length) return;

	if ($toolbar.find("button:contains('Stock Availability')").length > 0) return;

	let $target = $toolbar.find("button:contains('Add Multiple')").last();
	if (!$target.length) $target = $toolbar.find("button:contains('Add Row')").last();

	const btn = $(
		`<button type="button" class="btn btn-secondary btn-xs" style="margin-left: 10px;">${__(
			"Stock Availability"
		)}</button>`
	);
	btn.on("click", function () {
		const default_item = al_buraq.get_default_item_for_stock_availability(frm);
		al_buraq.open_stock_availability_dialog(frm, default_item);
	});

	if ($target.length > 0 && $target.parent().is($toolbar)) {
		btn.insertAfter($target);
	} else {
		$toolbar.append(btn);
	}
};

al_buraq.get_default_item_for_stock_availability = function (frm) {
	if (!frm || !frm.fields_dict.items || !frm.fields_dict.items.grid) return null;
	const items_grid = frm.fields_dict.items.grid;

	const open_row = frappe.ui.form.get_open_grid_form();
	if (open_row && open_row.grid === items_grid && open_row.doc && open_row.doc.item_code) {
		return open_row.doc.item_code;
	}
	if (frm._al_buraq_stock_avail_row_cdt && frm._al_buraq_stock_avail_row_cdn) {
		const current = (locals[frm._al_buraq_stock_avail_row_cdt] || {})[frm._al_buraq_stock_avail_row_cdn];
		if (current && current.item_code) return current.item_code;
	}
	if (frm.doc.items && frm.doc.items.length) {
		const last = frm.doc.items[frm.doc.items.length - 1];
		if (last && last.item_code) return last.item_code;
	}
	return null;
};

al_buraq.open_stock_availability_dialog = function (frm, default_item_code) {
	const company = frm.doc.company || frappe.defaults.get_default("company");

	const d = new frappe.ui.Dialog({
		title: __("Stock Availability"),
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
						filters: { company: company },
					};
				},
			},
			{
				fieldname: "item_name",
				label: __("Item Name"),
				fieldtype: "Data",
				read_only: 1,
			},
			{ fieldname: "results", fieldtype: "HTML" },
		],
		size: "extra-large",
		primary_action_label: __("Close"),
		primary_action: function () {
			d.hide();
		},
	});

	d.show();

	const _load = function (item_code) {
		if (!item_code) {
			d.set_value("item_name", "");
			d.fields_dict.results.$wrapper.html("");
			return;
		}
		frappe.db.get_value("Item", item_code, "item_name", function (r) {
			d.set_value("item_name", (r && r.item_name) || "");
		});
		al_buraq.fetch_stock_availability(item_code, company, d);
	};

	setTimeout(() => {
		if (d.fields_dict.item_code) {
			d.fields_dict.item_code.df.onchange = function () {
				_load(d.get_value("item_code"));
			};
			d.fields_dict.item_code.refresh();
		}
		if (default_item_code) {
			_load(default_item_code);
		}
	}, 200);
};

al_buraq.fetch_stock_availability = function (item_code, company, dialog) {
	dialog.fields_dict.results.$wrapper.html(
		'<div class="text-muted">' + __("Loading…") + "</div>"
	);

	frappe.call({
		method: "al_buraq.api.warehouse_stock.get_item_warehouse_stock",
		args: { item_code: item_code, company: company },
		callback: function (r) {
			const rows = r.message || [];
			if (!rows.length) {
				dialog.fields_dict.results.$wrapper.html(
					'<div class="text-muted">' + __("No stock found for this item.") + "</div>"
				);
				return;
			}
			dialog.fields_dict.results.$wrapper.html(
				al_buraq.render_stock_availability_table(rows)
			);
			setTimeout(() => al_buraq.setupStockAvailabilityFilters(dialog), 100);
		},
		error: function (err) {
			dialog.fields_dict.results.$wrapper.html(
				'<div class="text-danger">' +
					__("Error fetching stock: {0}", [err.message || err]) +
					"</div>"
			);
		},
	});
};

al_buraq.render_stock_availability_table = function (rows) {
	var out = [
		'<div class="mt-3">',
		'<table class="table table-bordered table-sm" id="al-buraq-stock-avail-table">',
		"<thead>",
		"<tr>",
		"<th>" + __("Warehouse") + "</th>",
		'<th class="text-right">' + __("Stock Qty") + "</th>",
		"<th>" + __("UOM") + "</th>",
		"</tr>",
		'<tr class="filter-row">',
		'<th><input type="text" class="form-control input-sm" placeholder="' + __("Filter Warehouse") + '"></th>',
		'<th><input type="text" class="form-control input-sm" placeholder="' + __("Filter Qty") + '"></th>',
		'<th><input type="text" class="form-control input-sm" placeholder="' + __("Filter UOM") + '"></th>',
		"</tr>",
		"</thead>",
		"<tbody>",
	].join("");

	rows.forEach(function (r) {
		const wh_name = frappe.utils.escape_html(r.warehouse_name || r.warehouse || "");
		const qty = format_number(r.stock_qty || 0, null, { precision: 2 });
		const uom = frappe.utils.escape_html(r.uom || "");
		const color = r.stock_qty > 0 ? "#28a745" : "#6c757d";
		const indicator = r.stock_qty > 0 ? "●" : "○";

		out += [
			"<tr>",
			`<td><span style="color:${color};margin-right:5px;font-size:12px;">${indicator}</span>${wh_name}</td>`,
			`<td class="text-right"><strong style="color:${color};">${qty}</strong></td>`,
			`<td>${uom}</td>`,
			"</tr>",
		].join("");
	});

	out += "</tbody></table></div>";
	return out;
};

al_buraq.setupStockAvailabilityFilters = function (dialog) {
	const table = dialog.fields_dict.results.$wrapper.find("#al-buraq-stock-avail-table")[0];
	if (!table) return;
	const inputs = table.querySelectorAll(".filter-row input");
	inputs.forEach(function (input) {
		if (input._filterHandler) input.removeEventListener("input", input._filterHandler);
		input._filterHandler = function () {
			al_buraq.applyAllStockAvailabilityFilters(dialog);
		};
		input.addEventListener("input", input._filterHandler);
	});
};

al_buraq.applyAllStockAvailabilityFilters = function (dialog) {
	const table = dialog.fields_dict.results.$wrapper.find("#al-buraq-stock-avail-table")[0];
	if (!table) return;
	const rows = table.querySelectorAll("tbody tr");
	const inputs = table.querySelectorAll(".filter-row input");
	rows.forEach(function (row) {
		let show = true;
		inputs.forEach(function (input, j) {
			const val = input.value.toLowerCase().trim();
			if (!val) return;
			const cell = row.cells[j];
			if (cell && (cell.textContent || "").toLowerCase().indexOf(val) === -1) show = false;
		});
		row.style.display = show ? "" : "none";
	});
};

// Full Sales and Purchase workflow — all doctypes with an items table.
const _al_buraq_stock_avail_doctypes = [
	// Sales workflow
	"Quotation",
	"Sales Order",
	"Delivery Note",
	"Sales Invoice",
	// Purchase workflow
	"Request for Quotation",
	"Supplier Quotation",
	"Purchase Order",
	"Purchase Receipt",
	"Purchase Invoice",
	// Supporting
	"Material Request",
];

_al_buraq_stock_avail_doctypes.forEach(function (doctype) {
	frappe.ui.form.on(doctype, {
		refresh: function (frm) {
			let attempts = 0;
			const maxAttempts = 8;
			const tryAddButton = function () {
				attempts++;
				if (frm.fields_dict.items && frm.fields_dict.items.grid) {
					al_buraq.add_stock_availability_button(frm);
					const $toolbar = frm.fields_dict.items.grid.wrapper.find(".grid-buttons");
					if ($toolbar.find("button:contains('Stock Availability')").length > 0) return;
				}
				if (attempts < maxAttempts) setTimeout(tryAddButton, 400);
			};
			setTimeout(tryAddButton, 800);
		},
		items_add: function (frm) {
			setTimeout(function () {
				al_buraq.add_stock_availability_button(frm);
			}, 800);
		},
	});
});
