import frappe
from frappe import _
from frappe.utils import getdate, nowdate

RECEIPT_PURPOSES = ("Material Receipt",)


def mark_received_temporary_items(doc, method=None):
	"""Clear the temporary flag once stock of the item is actually received (requirement 2.1.3).

	Runs on submit of Purchase Receipt, Purchase Invoice (only when it updates stock) and Stock
	Entry (Material Receipt). The Item record stays the same, so every quotation already pointing
	at it stays linked; the flag is cleared and the date recorded so the item can be completed.
	Cancelling the receipt does not set the flag again.
	"""
	if doc.doctype == "Purchase Invoice" and not doc.get("update_stock"):
		return
	if doc.doctype == "Stock Entry" and doc.get("purpose") not in RECEIPT_PURPOSES:
		return

	item_codes = {d.item_code for d in doc.get("items") or [] if d.item_code}
	if not item_codes:
		return

	temporary = frappe.get_all(
		"Item",
		filters={"name": ["in", list(item_codes)], "custom_is_temporary": 1},
		pluck="name",
	)
	received_on = getdate(doc.get("posting_date") or nowdate())
	for item_code in temporary:
		frappe.db.set_value(
			"Item",
			item_code,
			{"custom_is_temporary": 0, "custom_temp_received_on": received_on},
			update_modified=False,
		)
		frappe.get_doc("Item", item_code).add_comment(
			"Info",
			_("Stock received on {0} {1}. Temporary flag cleared; please complete the item details.").format(
				doc.doctype, doc.name
			),
		)
