// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

window.alBuraqCreateOffer = function (item, discount, expiry) {
	frappe.call({
		method: "al_buraq.api.expiry_offer.create_expiry_offer",
		args: {
			item_code: decodeURIComponent(item),
			discount_percent: discount,
			valid_upto: expiry,
			company: frappe.defaults.get_user_default("Company"),
		},
		freeze: true,
		callback: function (r) {
			if (r.message) {
				frappe.show_alert({ message: __("Draft offer {0} created. It stays switched off until you review it.", [r.message]), indicator: "green" });
				frappe.set_route("Form", "Pricing Rule", r.message);
			}
		},
	});
};

frappe.query_reports["Expiring Stock and Suggested Offers"] = {
	filters: [
		{ fieldname: "within_days", label: __("Expires Within (Days)"), fieldtype: "Int", description: __("Empty: the widest offer band") },
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "create_offer" && data && data.suggested_discount != null) {
			value = `<a href="#" onclick="alBuraqCreateOffer('${encodeURIComponent(data.item_code)}', ${data.suggested_discount}, '${data.expiry_date}'); return false;">${__("Create offer")}</a>`;
		}
		if (column.fieldname === "days_left" && data && data.days_left < 0) {
			value = `<span class="indicator-pill red">${__("Expired")}</span>`;
		}
		return value;
	},
};
