// Copyright (c) 2016, Rohit Industries Group Private Limited and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Production and Planning Report RIGPL"] = {
	"filters": [
	    {
			"fieldname":"from_date",
			"label": "From Date",
			"fieldtype": "Date",
			"required": 1,
			"default": frappe.datetime.get_today()
		},
	    {
			"fieldname":"to_date",
			"label": "To Date",
			"fieldtype": "Date",
			"required": 1,
			"default": frappe.datetime.get_today()
		},
	    {
			"fieldname":"operation",
			"label": "Operation",
			"fieldtype": "Link",
			"required": 0,
			"options": "Operation"
		},
	    {
			"fieldname":"jc_status",
			"label": "Job Card Status",
			"fieldtype": "Select",
			"required": 0,
			"options": "\nOpen\nWork In Progress",
			"default": "Work In Progress"
		},
		{
			"fieldname":"bm",
			"label": "Base Material",
			"fieldtype": "Link",
			"options": "Item Attribute Value",
			"reqd": 0,
			"ignore_link_validation": true,
			"get_query": function(){ return {query: "rigpl_erpnext.utils.attribute_query.attribute_bm_query"}}
		},
		{
			"fieldname":"tt",
			"label": "Tool Type",
			"fieldtype": "Link",
			"options": "Item Attribute Value",
			"reqd": 0,
			"ignore_link_validation": true,
			"get_query": function(){ return {query: "rigpl_erpnext.utils.attribute_query.attribute_tt_query"}}
		},
		{
			"fieldname":"series",
			"label": "Series",
			"fieldtype": "Link",
			"options": "Item Attribute Value",
			"reqd": 0,
			"ignore_link_validation": true,
			"get_query": function(){ return {query: "rigpl_erpnext.utils.attribute_query.attribute_series_query"}}
		},
		{
			"fieldname":"item",
			"label": "Item Code",
			"fieldtype": "Link",
			"options": "Item",
			"get_query": function(){ return {'filters': [['Item', 'has_variants','=', 0]]}}
		},
		{
			"fieldname":"sales_order",
			"label": "Sales Order",
			"fieldtype": "Link",
			"options": "Sales Order",
			"get_query": function(){ return {query: "rigpl_erpnext.rigpl_erpnext.doctype.create_bulk_process_sheet." +
			    "create_bulk_process_sheet.get_so_pending_for_process_sheet"}}
		},
		{
			"fieldname":"mach_eff_type",
			"label": "Efficiency Type",
			"fieldtype": "Select",
			"options": "\nDaily\nTotal",
			"default": "Total"
		},
		{
			"fieldname":"summary",
			"label": "Post Production Summary",
			"fieldtype": "Check",
			"default": 0
		},
		{
			"fieldname":"production_planning",
			"label": "Production Planning",
			"fieldtype": "Check",
			"default": 1
		},
		{
			"fieldname":"order_wise_summary",
			"label": "SO wise Summary",
			"fieldtype": "Check",
			"default": 0
		},
		{
			"fieldname":"op_time_analysis",
			"label": "Operation Time Analysis",
			"fieldtype": "Check",
			"default": 0
		},
		{
			"fieldname":"mach_eff",
			"label": "Machine Efficiency",
			"fieldtype": "Check",
			"default": 0
		}
	]
};
