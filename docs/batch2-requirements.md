# Batch 2 — client requirements 2.4.3, 2.2.3 (rest), 1.2, 1.4

Source: *ERPNext Functional Requirements, Al Buraq Holdings Group, 25 Oct 2026*. Builds on batch 1 (`docs/batch1-requirements.md`).

| Ref | What | Where |
|---|---|---|
| 2.4.3 | **Sales Price History** report (module Al Buraq, ref Sales Invoice). Filters: company, date range, sales person, customer, item, item group. **Detail** view: one row per invoice line with date, invoice, customer, sales person, item, delivery note, qty, UOM, rate and rate per stock UOM. **Item and Sales Person** view: per item and employee, invoices, qty, lowest / quantity-weighted average / highest / latest rate. Submitted, non-return invoices only; honours user permissions. Sales person = the invoice's *Sales Person* field, else the first row of its Sales Team. Roles: System Manager, Sales Master Manager, Sales Manager, Sales Supervisor, Accounts Manager, Accounts User, Auditor (Sales User is left out because the report compares employees). | `al_buraq/report/sales_price_history/` |
| 1.4 | Foreign-currency Purchase Orders at the rate of their date. See below. | `patches/set_up_foreign_currency_rates.py` |
| 1.2 | Nothing to build, it is standard. `tests/test_buying_acceptance.py` pins it: the call behind *Get Items From > Purchase Receipt*, given several receipts of one supplier, returns one Purchase Invoice; the receipts show as billed on submit. | tests only |
| 2.2.3 | No further change. See below. | — |

## 1.4 — what was wrong and what the patch does

The live site's rate provider is Frankfurter (ECB rates), which has **no AED**. Every foreign-currency order of the AED company therefore ended in "Unable to find exchange rate". ERPNext can use the dirham's peg to the dollar (Accounts Settings > *Allow Pegged Currencies Exchange Rates*, plus the Pegged Currencies table, already filled with AED, SAR, QAR, BHD, OMR, JOD), but:

> **ERPNext 15.118 – 15.121 returns the inverse for a direct pegged pair.** With the switch on and nothing else, USD to AED comes out as **0.2723** instead of **3.6725**, so a dollar order would be valued at about 7% of its real value. EUR, GBP, CNY... to AED are correct, because they go through the provider and multiply by the ratio.

The patch therefore does two things: turns the switch on, and writes each peg as Currency Exchange records in both directions dated 2000-01-01 (AED/USD, SAR/USD, ...). A stored record is found before the faulty code runs. It relies on *Allow Stale Exchange Rates* staying on (it is on today). Rates for other currencies come from the provider for the transaction date; a Currency Exchange record entered by hand wins for its dates.

Tests cover: the pegs in both directions with the provider switched off, a provider rate for the transaction date (mocked, request checked), the failure without the switch, manual rates applying from their date, and a USD Purchase Order valued at 3.6725. Worth reporting upstream to Frappe; not worked around inside ERPNext.

## 2.2.3 — what is left and why it stays

The default format of each document already carries the Delivery Note reference: Delivery Note, Sales Order (*Performa Invoice*), Sales Invoice (*Tax Invoice Format*) and every hand-built Al Buraq format. The formats still without it (*Detailed Tax Invoice*, *Simplified Tax Invoice*, *Tax Invoice*, *Sales Auditing Voucher*, *Sales Invoice Print*, *Sales Invoice Return*) are **standard formats shipped by other apps** and none is the default of any document on this site; editing them would be overwritten by the next app update. *Point of Sale* is a POS receipt. The Open Items reports are built around the delivery-to-invoice link.

## Deploying

`bench migrate` runs the patch (one Accounts Settings change, up to 12 Currency Exchange rows) and imports the report. No build step, no restart needed beyond the usual reload. Back up first.

## Tests

`bench --site <test-site> run-tests --app al_buraq`. The Sales Price History tests create the *Sales Person* custom field on Sales Invoice if the site lacks it (the live site has it, added by hand, and is not created by this app).
