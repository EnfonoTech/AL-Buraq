import frappe
from frappe.utils import add_days, cint, date_diff, flt, getdate, today


def get_tiers():
	"""Offer bands from Al Buraq Settings, soonest expiry first: [(days_to_expiry, discount_percent)]."""
	rows = frappe.get_cached_doc("Al Buraq Settings").get("expiry_offer_tiers") or []
	return sorted((cint(r.days_to_expiry), flt(r.discount_percent)) for r in rows)


def suggest_discount(days_left, tiers):
	"""The discount of the first band the batch falls into, or None.

	A batch that has already expired gets no suggestion: it should not be sold at all.
	"""
	if days_left < 0:
		return None
	for days, discount in tiers:
		if days_left <= days:
			return discount
	return None


def expiring_batches(within_days=None, item_group=None):
	"""Batches with stock that expire within `within_days` (default: the widest band), including
	those already expired, soonest first. Each row carries the suggested discount and the offer rate."""
	tiers = get_tiers()
	if within_days is None:
		within_days = max((days for days, _ in tiers), default=30)

	filters = {
		"disabled": 0,
		"batch_qty": [">", 0],
		"expiry_date": ["<=", add_days(today(), cint(within_days))],
	}
	batches = frappe.get_all(
		"Batch",
		filters=filters,
		fields=["name", "item", "item_name", "batch_qty", "expiry_date", "stock_uom"],
		order_by="expiry_date asc, name asc",
	)

	groups = {}
	if batches:
		groups = {
			i.name: i.item_group
			for i in frappe.get_all("Item", filters={"name": ["in", [b.item for b in batches]]}, fields=["name", "item_group"])
		}
	rates = selling_rates([b.item for b in batches])

	rows = []
	for batch in batches:
		if item_group and groups.get(batch.item) != item_group:
			continue
		days_left = date_diff(getdate(batch.expiry_date), getdate(today()))
		discount = suggest_discount(days_left, tiers)
		rate = rates.get(batch.item) or 0
		rows.append(
			{
				"item_code": batch.item,
				"item_name": batch.item_name,
				"batch": batch.name,
				"qty": flt(batch.batch_qty),
				"uom": batch.stock_uom,
				"expiry_date": batch.expiry_date,
				"days_left": days_left,
				"suggested_discount": discount,
				"selling_rate": rate,
				"offer_rate": flt(rate * (1 - discount / 100), 2) if discount is not None and rate else None,
			}
		)
	return rows


def selling_rates(item_codes):
	"""Latest selling Item Price per item, else the item's Standard Selling Rate."""
	if not item_codes:
		return {}
	rates = {}
	for price in frappe.get_all(
		"Item Price",
		filters={"item_code": ["in", item_codes], "selling": 1},
		fields=["item_code", "price_list_rate"],
		order_by="modified asc",
	):
		rates[price.item_code] = flt(price.price_list_rate)
	for item in frappe.get_all("Item", filters={"name": ["in", item_codes]}, fields=["name", "standard_rate"]):
		rates.setdefault(item.name, flt(item.standard_rate))
	return rates
