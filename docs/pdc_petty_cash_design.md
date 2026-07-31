# PDC & Petty Cash Tracking — Design / Field-Mapping Document

Prepared for: Hashir (client review) | Site: **buraq** (test/staging only) | Status: **DRAFT — pending client sign-off**

This document maps every field/calculation in `hvac trd.xlsx` (sheets: CHQ, MONTLY ALLOCATION, PETTY) to its
ERPNext equivalent, per the development brief. No code has been written yet — this is for review before build
starts.

---

## 1. CHQ sheet → Payment Entry (native fields, no new doctype)

| Excel column (CHQ sheet) | ERPNext field | Notes |
|---|---|---|
| PARTICULAR (party name) | `Payment Entry.party` | Supplier or Customer, depending on Direction |
| CHEQUE NO | `Payment Entry.reference_no` | Already exists natively |
| CHEQUE DATE | `Payment Entry.reference_date` | Already exists natively |
| AMOUNT | `Payment Entry.paid_amount` / `received_amount` | |
| REMARKS | `Payment Entry.remarks` | |
| Issued vs Received (implicit — two tables in the Excel) | `Payment Entry.payment_type` | `Pay` = Issued, `Receive` = Received |
| Month-wise totals / grand total | Report grouping (see §4) | Not stored — calculated |

**New field needed:** `pdc_status` (Select: Pending / Deposited / Cleared / Bounced) — does not exist natively.
Native `clearance_date` only gives a binary cleared/not-cleared state, not the 4-state flow the client uses.

**New field needed:** `pdc_transfer_entry` (Link to Journal Entry / Payment Entry) — links the PDC Payment Entry to
the entry that moves funds from the intermediary "Cheques in Hand" account to the real bank account on deposit.
Used for the validation you asked about (a PDC entry can't be marked Deposited without a linked transfer entry).

### Account setup (config, not code)
- Mode of Payment **"PDC Received"** → default account per company = new ledger **"Cheques in Hand – Received"**
  (Bank/Asset type)
- Mode of Payment **"PDC Issued"** → default account per company = new ledger **"Cheques in Hand – Issued"**
- Invoice is marked Paid the moment the PDC Payment Entry is made (matches client's current Excel behaviour —
  cheque received = shown as collected against the invoice immediately, before it's actually banked).

### Workflow (Frappe Workflow on Payment Entry, PDC entries only)
```
Pending → Deposited → Cleared
                    → Bounced
```
- **Pending → Deposited**: requires `pdc_transfer_entry` to be filled (validation) — this is the internal-transfer
  entry moving Cheques-in-Hand → Bank.
- **Deposited → Cleared**: set via the existing **Bank Clearance** tool (`clearance_date` on the transfer entry) —
  no new UI needed here, just wiring the workflow state to watch that field.
- **Deposited → Bounced**: just a status flag, matching current Excel behaviour (REMARKS is a plain text note,
  nothing automated). No auto-reopen of the invoice, no auto-added penalty/charge — the user follows up manually
  (reversing JE, re-invoicing, etc.) the same way they do today outside the sheet.

---

## 2. MONTLY ALLOCATION sheet → Fund Allocation Query Report

Source data: same PDC Payment Entries above — no separate doctype.

| Excel row/column | ERPNext source |
|---|---|
| "FUND IN BANK" running figure (per date) | Manual entry field per date (matches Excel — not a live GL pull) |
| Cheques listed under each FUND IN BANK date | PDC Payment Entries with `reference_date`/deposit date on/near that date, status Pending/Deposited |
| TOTAL RECEIVABLE | Sum of Received-direction PDCs due, matched against fund shortfall |
| TOTAL PAYABLE | Sum of Issued-direction PDCs due |
| Monthly totals (JUNE MONTH TOTAL, JULY MONTH TOTAL, …) | Grouped by month on `reference_date` |

Deliverable: one Query Report, filterable by date range, replicating this exact layout (party, cheque no, cheque
date, amount, running fund-in-bank, receivable/payable split).

**Decision:** kept as a manual "Expected Fund in Bank" entry per date, same as the Excel today — no live bank
balance integration. A small child table / doctype will hold these date + amount entries so the report can pull
them in alongside the PDC data.

---

## 3. PETTY sheet → Cash Denomination Entry (new DocType) + existing Cash accounts

### CASH BOX table (daily ledger)
This is already what the **General Ledger** of a Cash-type account gives you (opening balance, daily
debits/credits, running balance) — no new doctype needed here. We'll just make sure day-to-day cash
sales/deposits are posted against the designated petty cash account so the GL reproduces this table.

### Denomination table (notes/coins count)
| Excel column | New field on Cash Denomination Entry |
|---|---|
| Denomination value (0.25, 0.5, 1, 5, 10, 20, 50, 100, 200, 500, 1000) | Child table row: `denomination` (Currency) |
| Count | Child table row: `count` (Int) |
| Line total | Child table row: `amount` (calculated, read-only) |
| TOTAL CASH | Parent field `counted_total` (sum of child amounts) |

- **Petty Cash Settings** (small settings doctype, or a checkbox custom field on Account) — flags which Cash
  accounts represent petty cash, so the Denomination Entry knows which GL balance to reconcile against.
- **Reconciliation**: on submit, compare `counted_total` against the linked account's GL balance as of the entry
  date; show a mismatch warning (mirrors the Excel's implicit BALANCE vs TOTAL CASH check).

**Note:** the Excel also has a small "petty cash spend" list (Amazon, Shuhail, Buraq Elec, hvac Air Cond — page 6)
feeding into a "ZOHO" total (4200.75) — this is a reconciliation against entries already recorded in Zoho Books.
Informational only, out of scope for this build; no separate field needed.

---

## 4. Reports summary

| Report | Replicates | Built on |
|---|---|---|
| PDC Issued & Received (list/report view) | CHQ sheet | Payment Entry (filtered `payment_type` = PDC modes), grouped by month |
| Fund Allocation | MONTLY ALLOCATION sheet | Same Payment Entry data + Bank account GL balance |
| Cash Box | PETTY sheet (ledger) | Cash account General Ledger (native) |
| Denomination Reconciliation | PETTY sheet (note/coin count) | New Cash Denomination Entry doctype |

---

## 5. What's genuinely new (build list)

1. Custom fields on Payment Entry: `pdc_status`, `pdc_transfer_entry`
2. Frappe Workflow on Payment Entry (PDC entries only, via a condition on Mode of Payment)
3. Validation: `pdc_status` can't move to Deposited without `pdc_transfer_entry`; can't move to Cleared without
   `clearance_date` set on that transfer entry
4. New DocType: Expected Fund in Bank (date + amount, manual entry)
5. Query Report: Fund Allocation (PDC data + Expected Fund in Bank entries)
6. New DocType: Cash Denomination Entry (with child table for denominations)
7. Petty Cash Settings (or Account custom field) to flag petty cash accounts
8. Reconciliation check (Denomination Entry vs GL balance)

Everything else (cheque no/date capture, invoice payment against PDC, clearing via Bank Clearance, Cash Box
ledger) is standard ERPNext config — no code.

---

## 6. Sign-off

- [x] Bounce handling: status flag only, no automation — matches Excel (§1)
- [x] Fund-in-Bank: manual entry per date, no live GL pull — matches Excel (§2)
- [ ] Build proceeds on **buraq** site only
