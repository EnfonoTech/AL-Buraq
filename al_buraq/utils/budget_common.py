"""Shared data-access layer for the Budget Control & Forecasting Suite.

Every report/doctype in this suite (Committed Amount, Available to Spend,
Cash Forecast, Rolling Forecast, Budget Suggestion, Budget Scenario
Comparison) reads through the helpers here instead of querying Budget,
GL Entry, Purchase Order, or Material Request directly. This keeps the
query count fixed regardless of row count (no N+1 across reports) and
keeps the Monthly Distribution fallback and Cost Center roll-up
consistent with ERPNext's native Budget Variance Report so the numbers
reconcile.

Nothing in this module writes to the database.
"""

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Extract, Sum
from frappe.utils import cint, flt

from erpnext.controllers.trends import get_period_date_ranges, get_period_month_ranges

MONTHS = (
	"January",
	"February",
	"March",
	"April",
	"May",
	"June",
	"July",
	"August",
	"September",
	"October",
	"November",
	"December",
)

DIMENSIONS = {
	"Cost Center": {"field": "cost_center", "is_tree": True},
	"Project": {"field": "project", "is_tree": False},
}


def get_dimension_config(budget_against):
	"""Returns frappe._dict(field, is_tree) for a `budget_against` value.

	Custom Accounting Dimensions are intentionally not supported here:
	Purchase Order Item / Material Request Item / Payment Schedule don't
	reliably carry them, so Committed and Cash Forecast could not be
	computed consistently against a Budget held on one.
	"""
	config = DIMENSIONS.get(budget_against)
	if not config:
		frappe.throw(_("Budget Against {0} is not supported").format(budget_against))
	return frappe._dict(config)


def get_period_ranges(period, fiscal_year):
	"""Thin wrapper over erpnext.controllers.trends — do not reimplement."""
	return get_period_date_ranges(period, fiscal_year)


def get_period_month_ranges_for(period, fiscal_year):
	"""Thin wrapper over erpnext.controllers.trends — do not reimplement."""
	return get_period_month_ranges(period, fiscal_year)


def get_fiscal_years_between(from_fiscal_year, to_fiscal_year):
	"""One query. Ordered list of Fiscal Year names between two years
	(inclusive), matched by name range the same way native reports do."""
	return frappe.get_all(
		"Fiscal Year",
		filters=[["name", ">=", from_fiscal_year], ["name", "<=", to_fiscal_year]],
		order_by="year_start_date",
		pluck="name",
	)


def get_leaf_expense_accounts(company, root_types=None):
	"""One query. Leaf (non-group) accounts of the given root type(s)."""
	root_types = root_types or ["Expense"]
	return frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0, "root_type": ["in", root_types]},
		pluck="name",
	)


def get_dimension_rollup(budget_against, company):
	"""One query. {leaf_dimension_value: [self, ...ancestors]}.

	For Cost Center (a tree), a leaf's ancestors are every Cost Center
	whose [lft, rgt] interval contains the leaf's — this reproduces the
	native Budget Variance Report's roll-up, where a budget held on a
	parent Cost Center picks up all of its descendants' actuals. Project
	is not a tree, so each Project only rolls up to itself.
	"""
	dim = get_dimension_config(budget_against)
	if not dim.is_tree:
		names = frappe.get_all(budget_against, filters={"company": company}, pluck="name")
		return {name: [name] for name in names}

	rows = frappe.get_all(
		budget_against, filters={"company": company}, fields=["name", "lft", "rgt"]
	)
	rollup = {}
	for leaf in rows:
		rollup[leaf.name] = [
			row.name for row in rows if row.lft <= leaf.lft and row.rgt >= leaf.rgt
		]
	return rollup


def _get_distribution_percentage_map(distribution_names):
	"""One query. {monthly_distribution_name: {month_name: percentage}}."""
	if not distribution_names:
		return {}

	mdp = frappe.qb.DocType("Monthly Distribution Percentage")
	rows = (
		frappe.qb.from_(mdp)
		.select(mdp.parent, mdp.month, mdp.percentage_allocation)
		.where(mdp.parent.isin(list(distribution_names)))
		.run(as_dict=True)
	)

	distribution_map = {}
	for row in rows:
		distribution_map.setdefault(row.parent, {})[row.month] = flt(row.percentage_allocation)
	return distribution_map


def _month_percentage(monthly_distribution, distribution_map, month):
	"""Reproduces the native Budget Variance Report fallback exactly:
	no distribution at all -> even 100/12; a distribution that simply
	doesn't list this month -> 0, not an even split.
	"""
	if not monthly_distribution:
		return 100.0 / 12
	return distribution_map.get(monthly_distribution, {}).get(month, 0)


def get_budget_map(filters):
	"""2 queries. {(dimension, account): {fiscal_year: {month: amount}}}.

	`filters` requires: company, budget_against, from_fiscal_year,
	to_fiscal_year. Optional: budget_against_filter (list), account (list).
	"""
	dim = get_dimension_config(filters.budget_against)
	dim_field = dim.field

	budget = frappe.qb.DocType("Budget")
	budget_account = frappe.qb.DocType("Budget Account")

	query = (
		frappe.qb.from_(budget)
		.inner_join(budget_account)
		.on(budget_account.parent == budget.name)
		.select(
			budget[dim_field].as_("dimension"),
			budget.monthly_distribution,
			budget.fiscal_year,
			budget_account.account,
			budget_account.budget_amount,
		)
		.where(budget.docstatus == 1)
		.where(budget.company == filters.company)
		.where(budget.budget_against == filters.budget_against)
		.where(budget.fiscal_year[filters.from_fiscal_year : filters.to_fiscal_year])
	)
	if filters.get("budget_against_filter"):
		query = query.where(budget[dim_field].isin(filters.budget_against_filter))
	if filters.get("account"):
		query = query.where(budget_account.account.isin(filters.account))

	rows = query.run(as_dict=True)

	distribution_map = _get_distribution_percentage_map(
		{r.monthly_distribution for r in rows if r.monthly_distribution}
	)

	budget_map = {}
	for row in rows:
		if not row.dimension:
			continue
		year_map = budget_map.setdefault((row.dimension, row.account), {}).setdefault(
			row.fiscal_year, {}
		)
		for month in MONTHS:
			pct = _month_percentage(row.monthly_distribution, distribution_map, month)
			year_map[month] = flt(year_map.get(month, 0)) + flt(row.budget_amount) * pct / 100

	return budget_map


def get_actual_map(filters, accounts):
	"""1 query (+ 1 roll-up query already cached by caller).

	{(dimension, account): {fiscal_year: {month: actual}}}, rolled up
	through get_dimension_rollup so a leaf's activity also counts toward
	every budgeted ancestor.

	`accounts` must be a bounded, non-empty iterable — never issue an
	unfiltered GL scan.
	"""
	if not accounts:
		return {}

	dim = get_dimension_config(filters.budget_against)
	dim_field = dim.field

	gl = frappe.qb.DocType("GL Entry")
	rows = (
		frappe.qb.from_(gl)
		.select(
			gl[dim_field].as_("dimension"),
			gl.account,
			gl.fiscal_year,
			Extract("month", gl.posting_date).as_("month_no"),
			(Sum(gl.debit) - Sum(gl.credit)).as_("actual"),
		)
		.where(gl.company == filters.company)
		.where(gl.posting_date[_fy_start(filters.from_fiscal_year) : _fy_end(filters.to_fiscal_year)])
		.where(gl.is_cancelled == 0)
		.where(gl.docstatus == 1)
		.where(gl.account.isin(list(accounts)))
		.where(gl[dim_field].isnotnull())
		.where(gl[dim_field] != "")
		.groupby(gl[dim_field], gl.account, gl.fiscal_year, Extract("month", gl.posting_date))
		.run(as_dict=True)
	)

	rollup = get_dimension_rollup(filters.budget_against, filters.company)

	actual_map = {}
	for row in rows:
		month = MONTHS[cint(row.month_no) - 1]
		for ancestor in rollup.get(row.dimension, [row.dimension]):
			year_map = actual_map.setdefault((ancestor, row.account), {}).setdefault(row.fiscal_year, {})
			year_map[month] = flt(year_map.get(month, 0)) + flt(row.actual)

	return actual_map


def get_monthly_actual_map(filters, accounts):
	"""1 query. {(dimension, account): {"YYYY-MM": actual}}, rolled up
	through get_dimension_rollup.

	Unlike get_actual_map (fiscal-year + calendar-month name, for
	reconciling against a Budget's Monthly Distribution), this is keyed by
	absolute calendar month so a trailing N-month window can be sliced
	precisely even when it crosses a fiscal year boundary — used by the
	Budget Suggestion report's Moving Average / YoY Growth % methods.

	`filters` requires: company, budget_against, from_date, to_date.
	`accounts` must be a bounded, non-empty iterable — never issue an
	unfiltered GL scan.
	"""
	if not accounts:
		return {}

	dim = get_dimension_config(filters.budget_against)
	dim_field = dim.field

	gl = frappe.qb.DocType("GL Entry")
	rows = (
		frappe.qb.from_(gl)
		.select(
			gl[dim_field].as_("dimension"),
			gl.account,
			Extract("year", gl.posting_date).as_("year_no"),
			Extract("month", gl.posting_date).as_("month_no"),
			(Sum(gl.debit) - Sum(gl.credit)).as_("actual"),
		)
		.where(gl.company == filters.company)
		.where(gl.posting_date[filters.from_date : filters.to_date])
		.where(gl.is_cancelled == 0)
		.where(gl.docstatus == 1)
		.where(gl.account.isin(list(accounts)))
		.where(gl[dim_field].isnotnull())
		.where(gl[dim_field] != "")
		.groupby(gl[dim_field], gl.account, Extract("year", gl.posting_date), Extract("month", gl.posting_date))
		.run(as_dict=True)
	)

	rollup = get_dimension_rollup(filters.budget_against, filters.company)

	monthly_map = {}
	for row in rows:
		period_key = "{0:04d}-{1:02d}".format(cint(row.year_no), cint(row.month_no))
		for ancestor in rollup.get(row.dimension, [row.dimension]):
			month_map = monthly_map.setdefault((ancestor, row.account), {})
			month_map[period_key] = flt(month_map.get(period_key, 0)) + flt(row.actual)

	return monthly_map


def get_committed_map(filters):
	"""2 queries. {(dimension, account): {month: {"po": amt, "mr": amt}}}.

	`filters` requires: company, budget_against, fiscal_year (single year
	— committed amounts are always "as of now", not spread across a
	from/to range), commitment_basis ("Expected Date" or
	"Transaction Date"). Optional: budget_against_filter, account,
	include_material_requests (default True), only_expense_accounts
	(default True).
	"""
	dim = get_dimension_config(filters.budget_against)
	dim_field = dim.field
	year_start, year_end = frappe.get_cached_value(
		"Fiscal Year", filters.fiscal_year, ["year_start_date", "year_end_date"]
	)

	committed_map = {}
	rollup = get_dimension_rollup(filters.budget_against, filters.company)
	expense_accounts = (
		set(get_leaf_expense_accounts(filters.company))
		if filters.get("only_expense_accounts", True)
		else None
	)

	for row in get_po_committed_rows(filters, dim_field, year_start, year_end):
		_accumulate_committed(committed_map, rollup, row, "po", expense_accounts)

	if filters.get("include_material_requests", True):
		for row in get_mr_committed_rows(filters, dim_field, year_start, year_end):
			_accumulate_committed(committed_map, rollup, row, "mr", expense_accounts)

	return committed_map


def get_committed_map_by_year(filters, fiscal_years):
	"""{(dimension, account): {fiscal_year: {month: {"po": x, "mr": y}}}}.

	Committed amounts are point-in-time (an open PO/MR's schedule or
	transaction date falls in exactly one fiscal year), so this is a thin
	loop over get_committed_map per year rather than a genuine range
	query — one pair of PO/MR queries per fiscal year in the range, same
	as calling get_committed_map that many times.
	"""
	result = {}
	for fiscal_year in fiscal_years:
		year_filters = frappe._dict(filters)
		year_filters["fiscal_year"] = fiscal_year
		for key, month_map in get_committed_map(year_filters).items():
			result.setdefault(key, {})[fiscal_year] = month_map
	return result


def get_forecast_map(filters):
	"""1 query. {(dimension, account): {month: forecast_amount}}.

	`filters` requires: company, budget_against, fiscal_year. Optional:
	budget_against_filter, account, forecast_version (defaults to every
	active Forecast Revision when omitted).
	"""
	dim = get_dimension_config(filters.budget_against)
	dim_field = dim.field

	parent = frappe.qb.DocType("Forecast Revision")
	child = frappe.qb.DocType("Forecast Revision Detail")

	query = (
		frappe.qb.from_(parent)
		.inner_join(child)
		.on(child.parent == parent.name)
		.select(
			parent[dim_field].as_("dimension"),
			child.account,
			child.month,
			child.forecast_amount,
		)
		.where(parent.company == filters.company)
		.where(parent.fiscal_year == filters.fiscal_year)
		.where(parent.budget_against == filters.budget_against)
	)
	if filters.get("forecast_version"):
		query = query.where(parent.forecast_version == filters.forecast_version)
	else:
		query = query.where(parent.is_active == 1)
	if filters.get("budget_against_filter"):
		query = query.where(parent[dim_field].isin(filters.budget_against_filter))
	if filters.get("account"):
		query = query.where(child.account.isin(filters.account))

	rows = query.run(as_dict=True)

	forecast_map = {}
	for row in rows:
		if not row.dimension:
			continue
		month_map = forecast_map.setdefault((row.dimension, row.account), {})
		month_map[row.month] = flt(month_map.get(row.month, 0)) + flt(row.forecast_amount)

	return forecast_map


def _accumulate_committed(committed_map, rollup, row, leg, expense_accounts):
	if not row.dimension or not row.account:
		return
	if expense_accounts is not None and row.account not in expense_accounts:
		return
	for ancestor in rollup.get(row.dimension, [row.dimension]):
		month_map = committed_map.setdefault((ancestor, row.account), {})
		bucket = month_map.setdefault(row.month, {"po": 0.0, "mr": 0.0})
		bucket[leg] = flt(bucket[leg]) + flt(row.amount)


def get_po_committed_rows(filters, dim_field, year_start, year_end):
	"""One query. Row-level open-PO commitments — used both to build the
	aggregated committed map and, by the Committed Amount report, as the
	source for voucher-level detail rows. Extra fields beyond
	dimension/account/month/amount are harmless to map-building callers.
	"""
	poi = frappe.qb.DocType("Purchase Order Item")
	po = frappe.qb.DocType("Purchase Order")

	date_field = poi.schedule_date if filters.commitment_basis == "Expected Date" else po.transaction_date
	committed_amount = (poi.amount - poi.billed_amt) * po.conversion_rate
	pending_qty = Case().when(poi.rate > 0, (poi.amount - poi.billed_amt) / poi.rate).else_(0)

	query = (
		frappe.qb.from_(poi)
		.inner_join(po)
		.on(poi.parent == po.name)
		.select(
			poi[dim_field].as_("dimension"),
			poi.expense_account.as_("account"),
			Extract("month", date_field).as_("month_no"),
			committed_amount.as_("amount"),
			po.name.as_("voucher_no"),
			po.transaction_date,
			date_field.as_("date"),
			poi.item_code,
			pending_qty.as_("pending_qty"),
		)
		.where(po.docstatus == 1)
		.where(po.company == filters.company)
		.where(po.status != "Closed")
		.where(poi.amount > poi.billed_amt)
		.where(date_field[year_start:year_end])
	)
	if filters.get("budget_against_filter"):
		query = query.where(poi[dim_field].isin(filters.budget_against_filter))
	if filters.get("account"):
		query = query.where(poi.expense_account.isin(filters.account))

	rows = query.run(as_dict=True)
	for row in rows:
		row.month = MONTHS[cint(row.month_no) - 1] if row.month_no else None
		row.voucher_type = "Purchase Order"
	return [r for r in rows if r.month]


def get_mr_committed_rows(filters, dim_field, year_start, year_end):
	"""One query. Row-level pending-Material-Request commitments — see
	get_po_committed_rows for the shared map/detail rationale."""
	mri = frappe.qb.DocType("Material Request Item")
	mr = frappe.qb.DocType("Material Request")

	date_field = mri.schedule_date if filters.commitment_basis == "Expected Date" else mr.transaction_date
	pending_fraction = Case().when(mri.stock_qty > 0, (mri.stock_qty - mri.ordered_qty) / mri.stock_qty).else_(0)
	committed_amount = mri.amount * pending_fraction

	pending_qty = mri.qty - (mri.qty * mri.ordered_qty / mri.stock_qty)

	query = (
		frappe.qb.from_(mri)
		.inner_join(mr)
		.on(mri.parent == mr.name)
		.select(
			mri[dim_field].as_("dimension"),
			mri.expense_account.as_("account"),
			Extract("month", date_field).as_("month_no"),
			committed_amount.as_("amount"),
			mr.name.as_("voucher_no"),
			mr.transaction_date,
			date_field.as_("date"),
			mri.item_code,
			pending_qty.as_("pending_qty"),
		)
		.where(mr.docstatus == 1)
		.where(mr.company == filters.company)
		.where(mr.material_request_type == "Purchase")
		.where(mr.status.notin(["Stopped", "Cancelled"]))
		.where(mri.stock_qty > mri.ordered_qty)
		.where(date_field[year_start:year_end])
	)
	if filters.get("budget_against_filter"):
		query = query.where(mri[dim_field].isin(filters.budget_against_filter))
	if filters.get("account"):
		query = query.where(mri.expense_account.isin(filters.account))

	rows = query.run(as_dict=True)
	for row in rows:
		row.month = MONTHS[cint(row.month_no) - 1] if row.month_no else None
		row.voucher_type = "Material Request"
	return [r for r in rows if r.month]


def _fy_start(fiscal_year):
	return frappe.get_cached_value("Fiscal Year", fiscal_year, "year_start_date")


def _fy_end(fiscal_year):
	return frappe.get_cached_value("Fiscal Year", fiscal_year, "year_end_date")
