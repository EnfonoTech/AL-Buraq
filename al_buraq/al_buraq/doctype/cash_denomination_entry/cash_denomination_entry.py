import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class CashDenominationEntry(Document):
	def validate(self):
		self.validate_petty_cash_account()
		self.calculate_counted_total()
		self.set_gl_balance()
		self.set_all_cash_balances()
		self.flag_mismatch()

	def validate_petty_cash_account(self):
		if not frappe.db.get_value("Account", self.account, "is_petty_cash"):
			frappe.throw(
				_("{0} is not flagged as a Petty Cash account. Enable 'Is Petty Cash' on the Account first.").format(
					self.account
				)
			)

	def calculate_counted_total(self):
		total = 0
		for row in self.denominations:
			row.amount = flt(row.denomination) * flt(row.count)
			total += row.amount
		self.counted_total = total

	def set_gl_balance(self):
		from erpnext.accounts.utils import get_balance_on

		self.gl_balance = get_balance_on(
			account=self.account, date=self.posting_date, company=self.company
		)
		self.difference = flt(self.counted_total) - flt(self.gl_balance)

	def set_all_cash_balances(self):
		"""Show every Account Type = Cash account for this Company, with its GL
		balance as of the Date - so the Petty Cash count above can be seen
		alongside the company's full cash position."""
		from erpnext.accounts.utils import get_balance_on

		self.cash_balances = []
		total = 0

		accounts = frappe.get_all(
			"Account",
			filters={"company": self.company, "account_type": "Cash", "is_group": 0},
			fields=["name", "account_currency"],
			order_by="name",
		)
		for acc in accounts:
			balance = flt(get_balance_on(account=acc.name, date=self.posting_date, company=self.company))
			total += balance
			self.append(
				"cash_balances",
				{
					"account": acc.name,
					"account_currency": acc.account_currency,
					"balance": balance,
				},
			)

		self.total_cash_balance = total

	def flag_mismatch(self):
		if flt(self.difference):
			frappe.msgprint(
				_("Counted cash ({0}) does not match the books ({1}) — difference of {2}.").format(
					self.counted_total, self.gl_balance, self.difference
				),
				indicator="orange",
				title=_("Reconciliation Mismatch"),
			)
