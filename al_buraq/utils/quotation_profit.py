import frappe
from frappe import _
from frappe.utils import cint, flt


def set_quotation_profit(doc, method=None):
	"""Fill the internal profit block on a Quotation (requirement 2.1.2).

	Profit = net selling total (company currency) - item cost, where item cost is the row's
	valuation rate and, when that is empty, the item's last purchase rate (an out-of-stock item
	has no valuation rate yet). Alternative items are left out, as ERPNext leaves them out of the
	quotation totals. Non-stock items (services) legitimately cost nothing; stock items with no
	cost at all are listed in the profit note so an overstated profit is visible.
	"""
	rows = [d for d in doc.get("items") or [] if not d.get("is_alternative")]
	item_codes = list({d.item_code for d in rows if d.item_code})

	item_info = {}
	if item_codes:
		item_info = {
			r.name: r
			for r in frappe.get_all(
				"Item",
				filters={"name": ["in", item_codes]},
				fields=["name", "last_purchase_rate", "is_stock_item"],
			)
		}

	total_cost = 0.0
	uncosted = []
	for row in rows:
		stock_qty = flt(row.stock_qty) or flt(row.qty) * (flt(row.conversion_factor) or 1)
		info = item_info.get(row.item_code)
		cost_rate = flt(row.valuation_rate) or (flt(info.last_purchase_rate) if info else 0)
		if not cost_rate and info and cint(info.is_stock_item):
			uncosted.append(cint(row.idx))
		total_cost += cost_rate * stock_qty

	revenue = flt(doc.base_net_total)
	profit = revenue - total_cost

	doc.custom_total_profit = flt(profit, doc.precision("base_net_total"))
	doc.custom_profit_percent = flt(profit / revenue * 100, 2) if revenue else 0
	doc.custom_profit_note = (
		_("No cost found for row(s) {0}; profit is overstated for these.").format(
			", ".join(str(i) for i in uncosted)
		)
		if uncosted
		else ""
	)
