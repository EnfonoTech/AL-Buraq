import frappe
from erpnext.setup.utils import get_exchange_rate
from frappe.utils import add_days, flt, nowdate
from unittest.mock import MagicMock, patch

from al_buraq.patches import set_up_foreign_currency_rates
from al_buraq.tests.utils import COMPANY, AlBuraqTestCase, ensure_company, make_item, make_supplier

FLAG = "allow_pegged_currencies_exchange_rates"


def set_accounts_setting(field, value):
	frappe.db.set_single_value("Accounts Settings", field, value)
	frappe.clear_document_cache("Accounts Settings", "Accounts Settings")


def use_frankfurter_settings():
	"""The provider settings the buraq site has (Frankfurter v1, dated endpoint)."""
	settings = frappe.get_doc("Currency Exchange Settings")
	settings.service_provider = "Custom"
	settings.api_endpoint = "https://api.frankfurter.dev/v1/{transaction_date}"
	settings.set("req_params", [{"key": "base", "value": "{from_currency}"}, {"key": "symbols", "value": "{to_currency}"}])
	settings.set("result_key", [{"key": "rates"}, {"key": "{to_currency}"}])
	settings.save(ignore_permissions=True)
	frappe.clear_document_cache("Currency Exchange Settings", "Currency Exchange Settings")


def provider_returns(rate):
	response = MagicMock()
	response.json.return_value = {"rates": {"USD": rate}}
	return patch("requests.get", return_value=response)


class TestForeignCurrencyRates(AlBuraqTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_company()

	def setUp(self):
		frappe.db.delete("Currency Exchange", {"to_currency": ["in", ["AED", "USD"]]})
		set_accounts_setting("allow_stale", 1)
		set_accounts_setting(FLAG, 0)
		use_frankfurter_settings()

	def test_patch_turns_the_switch_on_and_writes_the_pegs_once(self):
		set_foreign = set_up_foreign_currency_rates

		set_foreign.execute()
		self.assertEqual(frappe.db.get_single_value("Accounts Settings", FLAG), 1)
		count = frappe.db.count("Currency Exchange", {"date": set_foreign.PEG_DATE})
		self.assertTrue(frappe.db.exists("Currency Exchange", {"from_currency": "USD", "to_currency": "AED", "date": set_foreign.PEG_DATE}))

		set_foreign.execute()
		self.assertEqual(frappe.db.count("Currency Exchange", {"date": set_foreign.PEG_DATE}), count)

	def test_the_dirham_peg_is_right_in_both_directions_without_the_provider(self):
		set_up_foreign_currency_rates.execute()

		with patch("requests.get", side_effect=AssertionError("provider must not be called")):
			self.assertAlmostEqual(flt(get_exchange_rate("USD", "AED", "2026-10-20")), 3.6725, places=4)
			self.assertAlmostEqual(flt(get_exchange_rate("AED", "USD", "2026-10-20")), 1 / 3.6725, places=6)
			self.assertAlmostEqual(flt(get_exchange_rate("USD", "SAR", nowdate())), 3.75, places=4)
			self.assertAlmostEqual(flt(get_exchange_rate("SAR", "USD", nowdate())), 1 / 3.75, places=6)

	def test_other_currency_to_dirham_uses_the_provider_dollar_rate_of_that_date(self):
		set_up_foreign_currency_rates.execute()
		date = add_days(nowdate(), -3)
		frappe.cache().delete(f"currency_exchange_rate_{date}:EUR:AED")

		with provider_returns(1.1193) as requests_get:
			rate = get_exchange_rate("EUR", "AED", date)

		self.assertAlmostEqual(rate, 1.1193 * 3.6725, places=4)
		requested = requests_get.call_args
		self.assertIn(date, requested.args[0])
		self.assertEqual(requested.kwargs["params"], {"base": "EUR", "symbols": "USD"})

	def test_without_the_switch_the_dirham_rate_cannot_be_found(self):
		date = add_days(nowdate(), -4)
		frappe.cache().delete(f"currency_exchange_rate_{date}:EUR:AED")

		response = MagicMock()
		response.json.return_value = {"rates": {}}  # the provider has no AED, so it answers without one
		with patch("requests.get", return_value=response):
			self.assertEqual(get_exchange_rate("EUR", "AED", date), 0.0)

	def test_a_manual_rate_applies_from_its_date_until_the_next_one(self):
		for date, rate in (("2026-01-01", 4.60), ("2026-06-01", 4.80)):
			frappe.get_doc(
				{
					"doctype": "Currency Exchange",
					"date": date,
					"from_currency": "GBP",
					"to_currency": "AED",
					"exchange_rate": rate,
					"for_buying": 1,
					"for_selling": 1,
				}
			).insert(ignore_permissions=True)

		with patch("requests.get", side_effect=AssertionError("provider must not be called")):
			self.assertEqual(flt(get_exchange_rate("GBP", "AED", "2026-03-15")), 4.60)
			self.assertEqual(flt(get_exchange_rate("GBP", "AED", "2026-06-01")), 4.80)
			self.assertEqual(flt(get_exchange_rate("GBP", "AED", "2026-07-20")), 4.80)

	def test_purchase_order_in_dollars_is_valued_at_the_rate_of_its_date(self):
		set_up_foreign_currency_rates.execute()
		item = make_item("AB-FX-1").name
		rate = get_exchange_rate("USD", "AED", nowdate())
		po = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"company": COMPANY,
				"supplier": make_supplier(),
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 7),
				"currency": "USD",
				"conversion_rate": rate,
				"items": [{"item_code": item, "qty": 5, "rate": 10, "schedule_date": add_days(nowdate(), 7)}],
			}
		)
		po.insert(ignore_permissions=True)

		self.assertEqual(po.currency, "USD")
		self.assertEqual(flt(po.grand_total), 50)
		self.assertAlmostEqual(flt(po.base_grand_total), 50 * 3.6725, places=2)
