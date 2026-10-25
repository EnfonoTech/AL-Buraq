// Requirement 2.1.3: create a temporary item from the Quotation for a product that is out of stock.
frappe.ui.form.on("Quotation", {
	refresh: function (frm) {
		if (frm.doc.docstatus !== 0) return;
		frm.add_custom_button(__("Temporary Item"), function () {
			al_buraq_new_temporary_item(frm);
		}, __("Create"));
	},
});

function al_buraq_new_temporary_item(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("New Temporary Item"),
		fields: [
			{ fieldname: "item_name", fieldtype: "Data", label: __("Item Name"), reqd: 1 },
			{ fieldname: "item_group", fieldtype: "Link", options: "Item Group", label: __("Item Group"), reqd: 1 },
			{ fieldname: "stock_uom", fieldtype: "Link", options: "UOM", label: __("UOM"), reqd: 1 },
			{ fieldname: "description", fieldtype: "Small Text", label: __("Description") },
		],
		primary_action_label: __("Create"),
		primary_action: function (values) {
			frappe.call({
				method: "al_buraq.api.temporary_item.create_temporary_item",
				args: Object.assign({}, values, { quotation: frm.is_new() ? null : frm.doc.name }),
				freeze: true,
				callback: function (r) {
					if (!r.message) return;
					dialog.hide();
					let row = (frm.doc.items || []).find(function (d) {
						return !d.item_code;
					});
					if (!row) row = frm.add_child("items");
					frappe.model.set_value(row.doctype, row.name, "item_code", r.message.item_code);
					frm.refresh_field("items");
					frappe.show_alert({
						message: __("Temporary item {0} added to the quotation", [r.message.item_code]),
						indicator: "green",
					});
				},
			});
		},
	});

	frappe.db.get_single_value("Stock Settings", "stock_uom").then(function (v) {
		if (v) dialog.set_value("stock_uom", v);
	});
	dialog.show();
}
