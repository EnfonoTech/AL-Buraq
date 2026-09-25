# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	message = get_message(data)
	chart = get_chart_data(data)
	return columns, data, message, chart


def get_columns():
	return [
		{"label": _("Title"), "fieldname": "name", "fieldtype": "Link", "options": "Recurring Cash Commitment", "width": 200},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 140},
		{"label": _("Cost Center"), "fieldname": "cost_center", "fieldtype": "Link", "options": "Cost Center", "width": 140},
		{"label": _("Direction"), "fieldname": "direction", "fieldtype": "Data", "width": 80},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Frequency"), "fieldname": "frequency", "fieldtype": "Data", "width": 100},
		{"label": _("Start Date"), "fieldname": "start_date", "fieldtype": "Date", "width": 100},
		{"label": _("End Date"), "fieldname": "end_date", "fieldtype": "Date", "width": 100},
		{"label": _("Is Active"), "fieldname": "is_active", "fieldtype": "Check", "width": 80},
		{"label": _("Confidence"), "fieldname": "confidence", "fieldtype": "Data", "width": 100},
		{"label": _("Classification"), "fieldname": "classification", "fieldtype": "Data", "width": 140},
		{"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 200},
	]


def get_data(filters):
	conditions = {"company": filters.company}

	if filters.get("cost_center"):
		conditions["cost_center"] = filters.cost_center
	if filters.get("direction"):
		conditions["direction"] = filters.direction
	if filters.get("classification"):
		conditions["classification"] = filters.classification
	if filters.get("confidence"):
		conditions["confidence"] = filters.confidence
	if filters.get("frequency"):
		conditions["frequency"] = filters.frequency
	if filters.get("status") == "Active":
		conditions["is_active"] = 1
	elif filters.get("status") == "Inactive":
		conditions["is_active"] = 0

	return frappe.get_all(
		"Recurring Cash Commitment",
		filters=conditions,
		fields=[
			"name",
			"company",
			"cost_center",
			"direction",
			"amount",
			"frequency",
			"start_date",
			"end_date",
			"is_active",
			"confidence",
			"classification",
			"remarks",
		],
		order_by="is_active desc, classification, name",
	)


def get_message(data):
	total_in = sum(flt(r.amount) for r in data if r.direction == "In")
	total_out = sum(flt(r.amount) for r in data if r.direction == "Out")
	return _("Total In: {0} | Total Out: {1} | Net: {2} (per the commitment's own Frequency, not annualised).").format(
		frappe.format_value(total_in, {"fieldtype": "Currency"}),
		frappe.format_value(total_out, {"fieldtype": "Currency"}),
		frappe.format_value(total_in - total_out, {"fieldtype": "Currency"}),
	)


def get_chart_data(data):
	if not data:
		return None

	classifications = []
	inflow_by_classification = {}
	outflow_by_classification = {}
	for row in data:
		classification = row.classification or _("Not Set")
		if classification not in inflow_by_classification:
			classifications.append(classification)
			inflow_by_classification[classification] = 0.0
			outflow_by_classification[classification] = 0.0
		if row.direction == "In":
			inflow_by_classification[classification] += flt(row.amount)
		else:
			outflow_by_classification[classification] += flt(row.amount)

	return {
		"data": {
			"labels": classifications,
			"datasets": [
				{"name": _("Inflow"), "values": [inflow_by_classification[c] for c in classifications]},
				{"name": _("Outflow"), "values": [outflow_by_classification[c] for c in classifications]},
			],
		},
		"type": "bar",
		"barOptions": {"stacked": 0},
	}
