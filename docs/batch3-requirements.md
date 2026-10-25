# Batch 3 — requirements 2.3.1–2.3.3, 1.1, 2.4.1, 3.2.1

Source: *ERPNext Functional Requirements, Al Buraq Holdings Group, 25 Oct 2026*. Builds on batches 1 and 2.

Everything here works from settings and tables the client edits. The defaults are our guesses and are listed under "Defaults to confirm"; none of them is hardcoded.

| Ref | What | Where |
|---|---|---|
| 2.3.1 | **Create → Job** on an Opportunity (the enquiry) makes a Job Record linked to it, with the departments of *Default Job Stages*. Asking again returns the existing Job. | `api/job.py`, `public/js/opportunity.js` |
| 2.3.2 | Job Record gains **Status**, **Progress** and a **Stages** table (department, status, assigned to, dates, remarks). Progress and status follow the stages; stages stay editable after submit. **Job Tracker** report: one row per job with a coloured status per department, "Waiting On", days open. | `al_buraq/doctype/job_record`, `report/job_tracker` |
| 2.3.3 | Daily: open enquiries with no Job after N days (default 3) are reported to the owner and the owner's superior. | `tasks/enquiry_reminders.py` |
| 1.1 | **Document Reminder Rule**: document type, date field, Before / On / After and days, filters, who is told. One daily digest per person per rule. Six rules are shipped. | `tasks/document_reminders.py`, `doctype/document_reminder_rule` |
| 2.4.1 | **Price and Discount Rule**: item group, customer group, quantity band, discount given automatically, maximum discount. Applied to Quotation, Sales Order and Sales Invoice rows. | `utils/price_discount.py`, `doctype/price_and_discount_rule` |
| 3.2.1 | **Expiry offer tiers** in Al Buraq Settings, the report **Expiring Stock and Suggested Offers** with a *Create offer* link (drafts a switched-off Pricing Rule), and the shipped rule *Batches about to expire*. | `utils/expiry_offers.py`, `api/expiry_offer.py`, `report/expiring_stock_and_suggested_offers` |

All settings are on one page: **Al Buraq Settings**.

## How the pieces behave

* **Job Record is now part of the app.** On the live site it was a database-only DocType (submittable, numbered `JOB-{YYYY}`, System Manager only, 0 records). The app now ships it under the same name with all its old fields plus the new ones; a migrate turns it into a normal app DocType and keeps its rows. Numbering becomes `JOB-2026-00001` (the old format could not number a second job). Permissions are given to Sales Manager, Sales Supervisor, Sales User and Accounts Manager. Because the live DocType has its own permission row, which Frappe lets override the file, `patches/grant_job_record_roles.py` adds the same roles there.
* **Superior** of an enquiry owner = *Reports To* on their Employee record. Without one, everyone holding the role named in the settings (Sales Supervisor).
* **Reminders are in-app notifications** (the bell). They are type *Alert*, which Frappe never turns into an email, so no mail can pile up for a mailbox that is configured later. *Also Send Reminders by Email* in the settings sends them as well, and only if an outgoing Email Account exists.
* **Reminder timing.** Before: from N days before the date until the date. On: the date is today. After: from N days after the date, every day until the document stops matching the filters (paid, submitted, ...). A person gets one message per rule per day however many documents match; the message links to the list.
* **Discount rules** pick the most specific match (item group counts 2, customer group counts 1), then the higher priority. A row with no discount gets the rule's automatic discount once; the row remembers the rule (`Discount Rule Applied`), so setting it back to 0 sticks. A discount above the rule's maximum is refused on save; Sales Managers and System Managers, and documents with the manager override ticked, may go over. The discount percentage is what is held to the maximum: ERPNext totals a row from it.
* **Expiry offers.** The suggested discount is the first tier whose days cover the days left; expired stock gets none. *Create offer* drafts a Pricing Rule for the item, discount, valid until the batch expiry, **switched off** until someone reviews it. It applies to the item, not to one batch (ERPNext prices by item).

## Defaults to confirm with Al Buraq

* An **Enquiry** is an ERPNext **Opportunity** (a Lead can sit in front of it).
* **Default Job Stages** is empty: the client lists the departments a job passes through. The site has the 14 standard departments to pick from.
* Enquiry reminder after **3 days**; fallback role **Sales Supervisor**.
* Shipped reminder rules (all in-app, all editable): Purchase Orders due for delivery (2 days before, Purchase Manager + owner); Purchase Invoices due for payment (3 days before, Accounts Manager); Sales Invoices overdue (1 day after, Accounts Manager + Sales Manager; **shipped switched off**, because 248 of the 265 invoices are overdue today and the digest would repeat that number every morning); Delivery Notes still in draft (1 day after, Stock Manager + owner); Quotations about to expire (2 days before, Sales Manager + owner); Batches about to expire (30 days before, Stock Manager).
* Expiry offer tiers: within **30 days 20%**, within **60 days 10%**.
* The **Price and Discount Rule table starts empty**: it needs the client's matrix. Nothing changes on a quotation until a rule exists.

## Deploying

`bench migrate` is the whole deploy: it syncs the new DocTypes, turns Job Record into an app DocType, imports the two reports, adds the item-row field, runs `grant_job_record_roles` and `seed_batch3_defaults`. **Back the site up first.** No build step (the only new JS is the Opportunity button, loaded with the form), and a normal worker reload picks up `hooks.py`.

**Five of the six reminder rules are enabled from the first daily run.** Today they would find 2 draft Delivery Notes and nothing else (no Purchase Order or Purchase Invoice is due, no Quotation is about to expire, no batches exist), so the first mornings are quiet. The Sales Invoices overdue rule is switched off. Change any of them in Document Reminder Rule.

Rehearsed on the scratch site from the live state: Job Record as a custom DocType with a row and its own permission row, migrated to the app DocType with the row kept, the sales roles able to create jobs, and no orphaned DocType.

**Gotcha found while testing:** Frappe looks up a DocType's controller by the name with spaces removed and the case kept, so *Price and Discount Rule* needs the class `PriceandDiscountRule`. With `PriceAndDiscountRule` the migrate reports the DocType as orphaned and deletes it.

## Tests

`bench --site <test-site> run-tests --app al_buraq` (106 at this point). New modules: `test_job_tracking`, `test_document_reminders`, `test_price_discount`, `test_expiry_offers`.
