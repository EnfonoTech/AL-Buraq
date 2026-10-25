# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today

CLOSED = ("Completed", "Cancelled")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	jobs = get_jobs(filters)
	stages = get_stages([j.name for j in jobs])

	if filters.get("department"):
		jobs = [j for j in jobs if any(s.department == filters.department for s in stages.get(j.name, []))]

	departments = []
	for job in jobs:
		for stage in stages.get(job.name, []):
			if stage.department not in departments:
				departments.append(stage.department)

	data = []
	for job in jobs:
		job_stages = stages.get(job.name, [])
		by_department = {s.department: s.status for s in job_stages}
		current = next((s for s in job_stages if s.status != "Done"), None)
		row = {
			"job": job.name,
			"job_name": job.job_name,
			"customer": job.customer,
			"opportunity": job.opportunity,
			"date": job.date,
			"status": job.status,
			"progress": job.progress,
			"days_open": date_diff(getdate(today()), getdate(job.date)) if job.date and job.status not in CLOSED else None,
			"current_stage": current and (current.department + (" (blocked)" if current.status == "Blocked" else "")),
		}
		for i, department in enumerate(departments):
			row[f"dept_{i}"] = by_department.get(department)
		data.append(row)

	return columns(departments), data


def get_jobs(filters):
	job_filters = {"docstatus": ["<", 2]}
	if filters.get("status"):
		job_filters["status"] = filters.status
	elif not filters.get("show_completed"):
		job_filters["status"] = ["not in", list(CLOSED)]
	if filters.get("customer"):
		job_filters["customer"] = filters.customer
	if filters.get("from_date"):
		job_filters["date"] = [">=", getdate(filters.from_date)]
	if filters.get("to_date"):
		job_filters["date"] = ["<=", getdate(filters.to_date)]
	if filters.get("from_date") and filters.get("to_date"):
		job_filters["date"] = ["between", [getdate(filters.from_date), getdate(filters.to_date)]]

	return frappe.get_list(
		"Job Record",
		filters=job_filters,
		fields=["name", "job_name", "customer", "opportunity", "date", "status", "progress"],
		order_by="date desc, name desc",
		limit_page_length=0,
	)


def get_stages(job_names):
	stages = {}
	if not job_names:
		return stages
	for stage in frappe.get_all(
		"Job Stage",
		filters={"parent": ["in", job_names], "parenttype": "Job Record"},
		fields=["parent", "department", "status", "idx"],
		order_by="parent, idx",
	):
		stages.setdefault(stage.parent, []).append(stage)
	return stages


def columns(departments):
	cols = [
		{"fieldname": "job", "label": _("Job"), "fieldtype": "Link", "options": "Job Record", "width": 130},
		{"fieldname": "job_name", "label": _("Job Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 160},
		{"fieldname": "opportunity", "label": _("Enquiry"), "fieldtype": "Link", "options": "Opportunity", "width": 130},
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "progress", "label": _("Progress %"), "fieldtype": "Percent", "width": 90},
		{"fieldname": "days_open", "label": _("Days Open"), "fieldtype": "Int", "width": 80},
		{"fieldname": "current_stage", "label": _("Waiting On"), "fieldtype": "Data", "width": 170},
	]
	for i, department in enumerate(departments):
		cols.append({"fieldname": f"dept_{i}", "label": department, "fieldtype": "Data", "width": 120})
	return cols
