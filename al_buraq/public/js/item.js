// Requirement 2.1.3: a temporary item can be merged into the real item once it exists.
frappe.ui.form.on("Item", {
	refresh: function (frm) {
		if (frm.is_new() || !frm.doc.custom_is_temporary) return;

		frm.dashboard.add_comment(
			__("Temporary item created for a quotation. It becomes a normal item automatically when stock is received, or merge it into the real item."),
			"orange",
			true
		);

		frm.add_custom_button(__("Merge into Existing Item"), function () {
			const dialog = new frappe.ui.Dialog({
				title: __("Merge {0} into", [frm.doc.name]),
				fields: [
					{
						fieldname: "target_item",
						fieldtype: "Link",
						options: "Item",
						label: __("Existing Item"),
						reqd: 1,
						get_query: function () {
							return {
								filters: { custom_is_temporary: 0, disabled: 0, name: ["!=", frm.doc.name] },
							};
						},
					},
					{
						fieldname: "note",
						fieldtype: "HTML",
						options: "<p class='text-muted'>" +
							__("Every quotation and order using this temporary item will point to the existing item, and the temporary item is deleted. This cannot be undone.") +
							"</p>",
					},
				],
				primary_action_label: __("Merge"),
				primary_action: function (values) {
					frappe.call({
						method: "al_buraq.api.temporary_item.merge_temporary_item",
						args: { temporary_item: frm.doc.name, target_item: values.target_item },
						freeze: true,
						callback: function (r) {
							if (!r.message) return;
							dialog.hide();
							frappe.set_route("Form", "Item", r.message);
						},
					});
				},
			});
			dialog.show();
		});
	},
});
