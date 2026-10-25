import frappe
from frappe.utils import flt

# Early enough that "the latest rate on or before the transaction date" always finds it.
PEG_DATE = "2000-01-01"
FIELD = "allow_pegged_currencies_exchange_rates"


def execute():
	"""Requirement 1.4: a Purchase Order in a foreign currency takes the exchange rate of its
	transaction date.

	The site's rate provider (Frankfurter, ECB rates) has no AED, so every foreign-currency order
	of an AED company came back as "Unable to find exchange rate". ERPNext can work around it with
	the dirham's peg to the US dollar: it asks the provider for the dollar rate of the transaction
	date and applies the ratio from the Pegged Currencies table. Two parts:

	1. switch that on (Accounts Settings), which gives EUR, GBP, CNY, ... against AED;
	2. write the pegs themselves (AED/USD, SAR/USD, ...) as Currency Exchange records, because
	   ERPNext 15.118 - 15.121 returns the inverse for a direct pegged pair (USD to AED comes out
	   as 0.2723 instead of 3.6725). A stored record is found before that code runs. This relies on
	   Accounts Settings > Allow Stale Exchange Rates staying on, as it is today.
	"""
	if frappe.get_meta("Accounts Settings").has_field(FIELD):
		if not frappe.db.get_single_value("Accounts Settings", FIELD):
			frappe.db.set_single_value("Accounts Settings", FIELD, 1)
			frappe.clear_document_cache("Accounts Settings", "Accounts Settings")

	write_peg_records()


def write_peg_records():
	pegs = frappe.get_all(
		"Pegged Currency Details",
		filters={"parent": "Pegged Currencies"},
		fields=["source_currency", "pegged_against", "pegged_exchange_rate"],
	)
	for peg in pegs:
		ratio = flt(peg.pegged_exchange_rate)  # units of the source currency per 1 of the anchor
		if not ratio:
			continue

		for from_currency, to_currency, rate in (
			(peg.pegged_against, peg.source_currency, ratio),
			(peg.source_currency, peg.pegged_against, 1 / ratio),
		):
			if frappe.db.exists(
				"Currency Exchange",
				{"from_currency": from_currency, "to_currency": to_currency, "date": PEG_DATE},
			):
				continue

			frappe.get_doc(
				{
					"doctype": "Currency Exchange",
					"date": PEG_DATE,
					"from_currency": from_currency,
					"to_currency": to_currency,
					"exchange_rate": rate,
					"for_buying": 1,
					"for_selling": 1,
				}
			).insert(ignore_permissions=True)
