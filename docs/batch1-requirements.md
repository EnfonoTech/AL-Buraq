# Batch 1 — client requirements 2.1.1, 2.1.2, 2.1.3, 2.2.3, 3.1.3

Source: *ERPNext Functional Requirements, Al Buraq Holdings Group, 25 Oct 2026*.

| Ref | What was built | Where |
|---|---|---|
| 2.1.2 | Internal profit block on Quotation: **Total Profit**, **Profit %**, **Profit Note**. Recalculated on every save. Profit = net selling total (company currency) − item cost. Cost is the row's valuation rate, else the item's last purchase rate. Stock items with no cost at all are listed in the note so an overstated profit is visible. Alternative items are left out, like the quotation totals. Profit % is on the net selling total (margin, not mark-up). | `utils/quotation_profit.py`, custom fields in `setup.py` |
| 2.1.3 | **Create → Temporary Item** on a draft Quotation. Sales users can use it without Item rights. The item is flagged *Temporary*, starts *Pending* in item approval, and is added to the quotation. The flag clears by itself when stock arrives (Purchase Receipt, Purchase Invoice with *Update Stock*, Stock Entry *Material Receipt*); the Item record stays the same, so the quotation stays linked. **Merge into Existing Item** on the Item form uses ERPNext's own Item merge when the real item already exists. | `api/temporary_item.py`, `utils/temporary_item.py`, `public/js/quotation.js`, `public/js/item.js` |
| 3.1.3 | **Maximum Selling Rate** on Item. Standard Selling Rate and selling Item Prices (converted to stock UOM) cannot exceed it. 0 = no limit. | `utils/selling_rate.py` |
| 2.1.1 | Terms and Conditions on a page of their own after the signature, in all three Quotation formats. `Quotation PF` keeps its hardcoded wording unless the quotation has Terms selected, in which case those replace it. | `patches/update_print_formats_batch1.py` |
| 2.2.3 | *Against Delivery Note* row added to `Tax Invoice Print Format` and `Performa Invoice` (same logic as the formats that already had it). | same patch |

## Decisions to confirm with Al Buraq

* **Who may see profit.** The profit block is on permlevel 2 and readable by Sales Manager, Sales Supervisor, Accounts Manager and System Manager (`patches/grant_quotation_profit_permlevel.py`). It is **not** in any customer print format, because a printed quotation goes to the customer. Adjust the roles in Role Permissions Manager.
* **Discount on grand total** is not reflected in profit (only discounts that change the net total are).
* **Max Selling Rate** is validated on Item and Item Price only. Quotations / Sales Orders / Invoices are not blocked above it; that needs a decision on who may override.
* **Temporary items** are not invoiceable until approved (existing *Block Unapproved Item* script). Cancelling the receipt does not set the flag again.

## Not touched

Sales Invoice formats built with the Print Format Builder (*Detailed Tax Invoice*, *Simplified Tax Invoice*, *Tax Invoice*), the formats without HTML (*Sales Auditing Voucher*, *Sales Invoice Print*), *Point of Sale* and *Sales Invoice Return* (empty) still have no Delivery Note row.

## Deploying

The patch rewrites the HTML of five existing Print Formats and does not keep the old HTML: **back the site up first**. It skips (and logs) any format whose expected anchor is missing, and is safe to run twice. Fields are created by `after_migrate`; the permlevel grant is a patch. Then `bench build --app al_buraq` for the two new JS files.

## Tests

```bash
bench --site <test-site> run-tests --app al_buraq --module al_buraq.tests.test_quotation_profit
bench --site <test-site> run-tests --app al_buraq --module al_buraq.tests.test_selling_rate
bench --site <test-site> run-tests --app al_buraq --module al_buraq.tests.test_temporary_item
bench --site <test-site> run-tests --app al_buraq --module al_buraq.tests.test_print_format_patch
```

The test site needs a company named **Al Buraq Test** (abbreviation `ABT`, AED), e.g. by running the setup wizard once. Known, unrelated: a fresh `install-app al_buraq` fails because the `Branch Configuration` Workspace fixture collides with the DocType of the same name.
