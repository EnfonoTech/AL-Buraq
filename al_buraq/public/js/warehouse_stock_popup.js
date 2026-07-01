// Warehouse Stock Inline Popup for al_buraq
// Shows warehouse stock below the items grid and allows creating Material Transfer requests.
// Applies to all transaction doctypes that carry a warehouse on their item lines:
//   Sales Invoice, Purchase Invoice, Sales Order, Purchase Order, Delivery Note, Purchase Receipt

frappe.provide("al_buraq");

al_buraq.stock_displays = {};

al_buraq.show_warehouse_stock = function (frm, item_row, load_all) {
	load_all = load_all || false;

	if (!item_row || !item_row.item_code) {
		al_buraq.hide_stock_display(frm);
		return;
	}

	if (!frappe.meta.has_field(item_row.doctype, "warehouse")) {
		al_buraq.hide_stock_display(frm);
		return;
	}

	const company = frm.doc.company;
	if (!company) {
		al_buraq.hide_stock_display(frm);
		return;
	}

	const current_row = locals[item_row.doctype][item_row.name];
	const warehouse = current_row ? (current_row.warehouse || "") : "";

	const api_args = {
		item_code: item_row.item_code,
		company: company,
		target_warehouse: warehouse || null,
	};

	if (!load_all) {
		api_args.limit = 5;
	}

	frappe.call({
		method: "al_buraq.api.warehouse_stock.get_item_warehouse_stock",
		args: api_args,
		callback: function (r) {
			if (r.message && r.message.length > 0) {
				al_buraq.render_stock_display(
					frm,
					item_row.item_code,
					r.message,
					warehouse,
					item_row.name,
					load_all,
					item_row.doctype
				);
			} else {
				al_buraq.hide_stock_display(frm);
			}
		},
		error: function () {
			al_buraq.hide_stock_display(frm);
		},
	});
};

al_buraq.render_stock_display = function (frm, item_code, stock_data, target_warehouse, item_row_name, is_all_loaded, item_cdt) {
	if (!frm.fields_dict.items || !frm.fields_dict.items.grid) return;

	const grid = frm.fields_dict.items.grid;
	const grid_wrapper = grid.wrapper;

	al_buraq.hide_stock_display(frm);

	let $container = grid_wrapper.find(".al-buraq-stock-display");
	if (!$container.length) {
		$container = $(
			'<div class="al-buraq-stock-display" style="margin-top: 8px; padding: 8px; background-color: #f9f9f9; border: 1px solid #d1d8dd; border-radius: 4px;"></div>'
		);
		grid_wrapper.append($container);
	}

	let target_warehouse_name = "";
	if (target_warehouse) {
		const target_wh = stock_data.find(function (item) {
			return item.warehouse === target_warehouse;
		});
		target_warehouse_name = target_wh ? (target_wh.warehouse_name || target_warehouse) : target_warehouse;
	}

	const visible_data = stock_data.slice(0, 5);
	const hidden_data = is_all_loaded ? stock_data.slice(5) : [];
	const has_more = is_all_loaded ? hidden_data.length > 0 : stock_data.length >= 5;

	const display_id = "al_stock_" + frm.doctype.replace(/\s/g, "_") + "_" + item_row_name.replace(/-/g, "_");

	let show_toggle_button = false;
	let button_text = "";
	let button_action = "";

	if (has_more && !is_all_loaded) {
		show_toggle_button = true;
		button_text = __("Show All");
		button_action = "load_all";
	} else if (is_all_loaded && stock_data.length > 5) {
		show_toggle_button = true;
		button_text = __("Show Less");
		button_action = "toggle_view";
	}

	let html = `
		<div style="margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center;">
			<div>
				<strong style="font-size: 14px;">${__("Stock Availability")} — ${frappe.utils.escape_html(item_code)}</strong>
				${target_warehouse ? `<span style="font-size: 12px; color: #666; margin-left: 8px;">→ ${frappe.utils.escape_html(target_warehouse_name)}</span>` : ""}
			</div>
			${show_toggle_button ? `
			<button class="btn btn-xs btn-link ${display_id}_toggle_btn"
				data-action="${button_action}"
				style="padding: 2px 6px; font-size: 12px; color: #007bff; text-decoration: none; margin-left: auto;">
				${button_text}
			</button>
			` : ""}
		</div>
		<div style="max-height: 300px; overflow-y: auto;">
			<table class="table table-bordered" style="margin: 0; background-color: white; font-size: 13px;">
				<thead>
					<tr style="background-color: #f5f5f5;">
						<th style="padding: 6px 8px; width: 55%; font-size: 13px;">${__("Warehouse")}</th>
						<th style="padding: 6px 8px; text-align: right; width: 25%; font-size: 13px;">${__("Stock Qty")}</th>
						<th style="padding: 6px 8px; text-align: center; width: 20%; font-size: 13px;">${__("Action")}</th>
					</tr>
				</thead>
				<tbody id="${display_id}_tbody">
	`;

	if (!stock_data.length) {
		html += `
			<tr>
				<td colspan="3" style="padding: 10px; text-align: center; color: #999; font-size: 13px;">
					${__("No warehouses with stock available")}
				</td>
			</tr>
		`;
	} else {
		const _render_row = function (item, extra_class) {
			const stock_color = item.stock_qty > 0 ? "#28a745" : "#6c757d";
			const indicator = item.stock_qty > 0 ? "●" : "○";
			const is_target = item.warehouse === target_warehouse;
			const row_bg = is_target ? "#e3f2fd" : "white";
			const wh_name = frappe.utils.escape_html(item.warehouse_name || item.warehouse);
			const wh_raw = frappe.utils.escape_html(item.warehouse);
			const wh_name_raw = frappe.utils.escape_html(item.warehouse_name || item.warehouse);
			const item_code_escaped = frappe.utils.escape_html(item_code);
			const to_wh_escaped = frappe.utils.escape_html(target_warehouse);
			const to_wh_name_escaped = frappe.utils.escape_html(target_warehouse_name);

			return `
				<tr class="${display_id}_row${extra_class ? " " + extra_class : ""}" style="background-color: ${row_bg};">
					<td style="padding: 6px 8px;">
						<span style="color: ${stock_color}; margin-right: 5px; font-size: 12px;">${indicator}</span>
						<span style="font-size: 13px;">${wh_name}</span>
						${is_target ? '<span style="color: #2196f3; margin-left: 5px; font-size: 12px;">(Target)</span>' : ""}
					</td>
					<td style="padding: 6px 8px; text-align: right;">
						<span style="color: ${stock_color}; font-weight: bold; font-size: 13px;">
							${format_number(item.stock_qty, null, { precision: 2 })}
						</span>
					</td>
					<td style="padding: 6px 8px; text-align: center;">
						${is_target
							? '<span style="color: #999; font-size: 12px;">—</span>'
							: `<button class="btn btn-xs btn-primary request-item-btn"
								data-item-code="${item_code_escaped}"
								data-from-warehouse="${wh_raw}"
								data-from-warehouse-name="${wh_name_raw}"
								data-to-warehouse="${to_wh_escaped}"
								data-to-warehouse-name="${to_wh_name_escaped}"
								data-item-row-name="${frappe.utils.escape_html(item_row_name)}"
								style="padding: 3px 10px; font-size: 12px;">
								${__("Request Items")}
							</button>`
						}
					</td>
				</tr>
			`;
		};

		visible_data.forEach(function (item) {
			html += _render_row(item, "");
		});

		if (is_all_loaded && hidden_data.length > 0) {
			hidden_data.forEach(function (item) {
				html += _render_row(item, display_id + "_hidden_row");
			});
		}
	}

	html += `</tbody></table></div>`;
	$container.html(html);
	$container.show();

	al_buraq.stock_displays[frm.doctype + "_" + frm.docname] = $container;

	// Toggle button
	const $toggle_btn = $container.find(`.${display_id}_toggle_btn`);
	if ($toggle_btn.length) {
		const btn_action = $toggle_btn.data("action");
		let is_expanded = btn_action === "toggle_view";

		$toggle_btn.on("click", function () {
			if (btn_action === "load_all") {
				$toggle_btn.prop("disabled", true).html(__("Loading..."));
				const item_row = locals[item_cdt] && locals[item_cdt][item_row_name];
				if (item_row && item_row.item_code) {
					al_buraq.show_warehouse_stock(frm, item_row, true);
				}
			} else if (btn_action === "toggle_view") {
				const $hidden_rows = $container.find(`.${display_id}_hidden_row`);
				if (is_expanded) {
					$hidden_rows.hide();
					$toggle_btn.html(__("Show All"));
					is_expanded = false;
				} else {
					$hidden_rows.show();
					$toggle_btn.html(__("Show Less"));
					is_expanded = true;
				}
			}
		});
	}

	// Request Items buttons
	$container.find(".request-item-btn").on("click", function () {
		const $btn = $(this);
		al_buraq.create_material_request(
			frm,
			$btn.data("item-code"),
			$btn.data("from-warehouse"),
			$btn.data("from-warehouse-name"),
			$btn.data("to-warehouse"),
			$btn.data("to-warehouse-name")
		);
	});
};

al_buraq.hide_stock_display = function (frm) {
	const key = frm.doctype + "_" + frm.docname;
	const $display = al_buraq.stock_displays[key];
	if ($display && $display.length) {
		$display.hide();
	}
};

al_buraq.create_material_request = function (frm, item_code, from_warehouse, from_warehouse_name, to_warehouse, to_warehouse_name) {
	const dialog = new frappe.ui.Dialog({
		title: __("Create Material Transfer Request"),
		fields: [
			{ fieldtype: "Data", fieldname: "item_code", label: __("Item Code"), default: item_code, read_only: 1 },
			{ fieldtype: "Data", fieldname: "from_warehouse", label: __("From Warehouse"), default: from_warehouse_name || from_warehouse, read_only: 1 },
			{ fieldtype: "Data", fieldname: "to_warehouse", label: __("To Warehouse"), default: to_warehouse_name || to_warehouse, read_only: 1 },
			{ fieldtype: "Float", fieldname: "qty", label: __("Quantity"), default: 1, reqd: 1 },
			{
				fieldtype: "Date",
				fieldname: "schedule_date",
				label: __("Required Date"),
				default: frappe.datetime.add_days(frappe.datetime.get_today(), 7),
				reqd: 1,
			},
		],
		primary_action_label: __("Create"),
		primary_action: function () {
			const values = dialog.get_values();
			if (!values) return;

			frappe.call({
				method: "al_buraq.api.material_request.create_material_request",
				args: {
					item_code: item_code,
					from_warehouse: from_warehouse,
					to_warehouse: to_warehouse,
					qty: values.qty,
					schedule_date: values.schedule_date,
					material_request_type: "Material Transfer",
					company: frm.doc.company,
				},
				callback: function (r) {
					if (r.message) {
						frappe.show_alert({
							message: __("Material Request {0} created and submitted", [r.message]),
							indicator: "green",
						});
					}
					dialog.hide();
				},
				error: function () {
					frappe.show_alert({ message: __("Error creating Material Request"), indicator: "red" });
				},
			});
		},
	});

	dialog.show();
};

// ─── Per-child-doctype field event hooks ─────────────────────────────────────
// Only applied to doctypes that carry a warehouse field on their item rows.

const _al_buraq_popup_item_doctypes = [
	"Sales Invoice Item",
	"Purchase Invoice Item",
	"Sales Order Item",
	"Purchase Order Item",
	"Delivery Note Item",
	"Purchase Receipt Item",
];

_al_buraq_popup_item_doctypes.forEach(function (child_doctype) {
	frappe.ui.form.on(child_doctype, {
		item_code: function (frm, cdt, cdn) {
			const item_row = locals[cdt][cdn];
			al_buraq._current_popup_row = item_row;
			if (item_row.item_code && frappe.meta.has_field(item_row.doctype, "warehouse") && frm.doc.company) {
				clearTimeout(item_row._al_buraq_stock_timeout);
				item_row._al_buraq_stock_timeout = setTimeout(function () {
					al_buraq.show_warehouse_stock(frm, item_row);
				}, 300);
			} else {
				al_buraq.hide_stock_display(frm);
			}
		},

		// Re-show after ERPNext refreshes the grid on item fetch
		item_name: function (frm, cdt, cdn) {
			const item_row = locals[cdt][cdn];
			al_buraq._current_popup_row = item_row;
			if (item_row.item_code && frappe.meta.has_field(item_row.doctype, "warehouse") && frm.doc.company) {
				clearTimeout(item_row._al_buraq_stock_timeout);
				item_row._al_buraq_stock_timeout = setTimeout(function () {
					al_buraq.show_warehouse_stock(frm, item_row);
				}, 100);
			}
		},

		item_code_focus: function (frm, cdt, cdn) {
			const item_row = locals[cdt][cdn];
			if (item_row && item_row.item_code && frappe.meta.has_field(item_row.doctype, "warehouse") && frm.doc.company) {
				al_buraq._current_popup_row = item_row;
				clearTimeout(item_row._al_buraq_stock_timeout);
				item_row._al_buraq_stock_timeout = setTimeout(function () {
					al_buraq.show_warehouse_stock(frm, item_row);
				}, 100);
			}
		},

		warehouse: function (frm, cdt, cdn) {
			const item_row = locals[cdt][cdn];
			al_buraq._current_popup_row = item_row;
			if (item_row.item_code && frappe.meta.has_field(item_row.doctype, "warehouse") && frm.doc.company) {
				clearTimeout(item_row._al_buraq_stock_timeout);
				item_row._al_buraq_stock_timeout = setTimeout(function () {
					al_buraq.show_warehouse_stock(frm, item_row);
				}, 300);
			}
		},

		form_render: function (frm, cdt, cdn) {
			const item_row = locals[cdt][cdn];
			if (item_row && item_row.item_code && frm.doc.company && frappe.meta.has_field(item_row.doctype, "warehouse")) {
				al_buraq._current_popup_row = item_row;
				clearTimeout(item_row._al_buraq_stock_timeout);
				item_row._al_buraq_stock_timeout = setTimeout(function () {
					al_buraq.show_warehouse_stock(frm, item_row);
				}, 200);
			}
		},
	});
});

// ─── Per-parent-form setup ────────────────────────────────────────────────────

function _al_buraq_setup_item_code_listeners(frm) {
	if (!frm.fields_dict.items || !frm.fields_dict.items.grid) return;
	const grid = frm.fields_dict.items.grid;

	grid.wrapper.on(
		"click focus",
		"[data-fieldname='item_code'] input, [data-fieldname='item_code'] .link-field",
		function () {
			const $row = $(this).closest(".grid-row");
			const idx = $row.attr("data-idx");
			if (idx && frm.doc.items) {
				const item_row = frm.doc.items.find(function (r) { return r.idx == idx; });
				if (item_row && item_row.item_code && frm.doc.company && frappe.meta.has_field(item_row.doctype, "warehouse")) {
					al_buraq._current_popup_row = item_row;
					clearTimeout(item_row._al_buraq_stock_timeout);
					item_row._al_buraq_stock_timeout = setTimeout(function () {
						al_buraq.show_warehouse_stock(frm, item_row);
					}, 100);
				}
			}
		}
	);
}

function _al_buraq_setup_hide_on_outside_click(frm) {
	if (!frm.fields_dict.items || !frm.fields_dict.items.grid) return;
	const $grid_wrapper = frm.fields_dict.items.grid.wrapper;

	$grid_wrapper.off("focusout.al_buraq_stock");
	if (frm.wrapper) $(frm.wrapper).off("click.al_buraq_stock");

	$grid_wrapper.on("focusout.al_buraq_stock", function () {
		setTimeout(function () {
			const active = document.activeElement;
			if (!active || !$grid_wrapper[0].contains(active)) {
				al_buraq.hide_stock_display(frm);
			}
		}, 150);
	});

	if (frm.wrapper) {
		$(frm.wrapper).on("click.al_buraq_stock", function (e) {
			if (!$grid_wrapper.length || !$grid_wrapper[0].contains(e.target)) {
				al_buraq.hide_stock_display(frm);
			}
		});
	}
}

const _al_buraq_popup_parent_forms = [
	"Sales Invoice",
	"Purchase Invoice",
	"Sales Order",
	"Purchase Order",
	"Delivery Note",
	"Purchase Receipt",
];

_al_buraq_popup_parent_forms.forEach(function (doctype) {
	frappe.ui.form.on(doctype, {
		refresh: function (frm) {
			_al_buraq_setup_item_code_listeners(frm);
			al_buraq.hide_stock_display(frm);
			_al_buraq_setup_hide_on_outside_click(frm);
		},
	});
});
