# -*- coding: utf-8 -*-
# Copyright (c) 2020, Rohit Industries Group Private Limited and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from rigpl_erpnext.utils.item_utils import get_desc, check_text_attributes
from frappe.model.document import Document


class BOMTemplateRIGPL(Document):
    def validate(self):
        self.validate_length_oal()
        if self.item_template:
            it_doc = frappe.get_doc("Item", self.item_template)
            if it_doc.has_variants != 1:
                frappe.throw("{} is not a Template and Only Item Templates are Allowed in {}".format(
                    frappe.get_desk_link("Item", self.item_template), self.name))
            if it_doc.include_item_in_manufacturing != 1:
                frappe.throw("{} is not Allowed for Manufacturing in {}".
                             format(frappe.get_desk_link("Item", self.item_template), self.name))
        self.validate_restriction_rules("rm_restrictions")
        self.validate_restriction_rules("fg_restrictions")
        self.validate_restriction_rules("wip_restrictions")
        self.validate_operations()
        self.generate_title()
        if self.routing:
            routing_dict = {}
            if not self.operations:
                routing_doc = frappe.get_doc('Routing', self.routing)
                # This is how you add data in Child table.
                for d in routing_doc.operations:
                    routing_dict["idx"] = d.idx
                    routing_dict["operation"] = d.operation
                    routing_dict["workstation"] = d.workstation
                    routing_dict["description"] = d.description
                    routing_dict["hour_rate"] = d.hour_rate
                    routing_dict["time_in_mins"] = d.time_in_mins
                    routing_dict["batch_size"] = d.batch_size
                    routing_dict["source_warehouse"] = d.source_warehouse
                    routing_dict["target_warehouse"] = d.target_warehouse
                    routing_dict["allow_consumption_of_rm"] = d.allow_consumption_of_rm
                    routing_dict["allow_production_of_wip_materials"] = d.allow_production_of_wip_materials
                    self.append("operations", routing_dict.copy())
        else:
            frappe.throw('Routing is Mandatory for {}'.format(self.name))
        for d in self.operations:
            if d.source_warehouse:
                if d.target_warehouse:
                    d.transfer_entry = 1
                else:
                    d.transfer_entry = 0
            else:
                d.transfer_entry = 0

            op_doc = frappe.get_doc("Operation", d.operation)
            if op_doc.is_subcontracting == 1:
                d.target_warehouse = op_doc.sub_contracting_warehouse
            if d.batch_size_based_on_formula == 1 and not d.batch_size_formula:
                frappe.throw("Batch Size Based on Formula but Formula is Missing for Row# {} in Operation Table".format(
                    d.idx))
            if d.time_based_on_formula == 1 and not d.operation_time_formula:
                frappe.throw("Operation Time Based on Formula but Formula is Missing for Row# {}  in Operation "
                             "Table".format(d.idx))
            if d.idx == len(self.operations):
                d.final_operation = 1
            else:
                d.final_operation = 0
            if d.final_operation == 1 and not d.final_warehouse:
                frappe.msgprint("Please set the Final Warehouse in Row# {} of Operations Table for "
                                "Operation {}".format(d.idx, d.operation))

    def validate_length_oal(self):
        if self.length_formula == 1:
            fg_oal, rm_oal, wip_oal = 0, 0, 0
            for d in self.fg_restrictions:
                if d.renamed_field_name == 'oal':
                    fg_oal += 1
            for d in self.rm_restrictions:
                if d.renamed_field_name == 'oal':
                    rm_oal += 1
            for d in self.wip_restrictions:
                if d.renamed_field_name == 'oal':
                    wip_oal += 1
            if self.fg_restrictions and fg_oal != 1:
                frappe.throw(f"In Finished Restrictions Table 1 Field and Only 1 Field should have OAL as its renamed "
                             f"Field since {self.name} has Length Formula Checked. "
                             f"The Table has {fg_oal} fields marked with oal")
            if self.rm_restrictions and rm_oal != 1:
                frappe.throw(f"In RM Restrictions Table 1 Field and Only 1 Field should have OAL as its renamed "
                             f"Field since {self.name} has Length Formula Checked. "
                             f"The Table has {rm_oal} fields marked with oal")
            if self.wip_restrictions and wip_oal != 1:
                frappe.throw(f"In WIP Restrictions Table 1 Field and Only 1 Field should have OAL as its renamed "
                             f"Field since {self.name} has Length Formula Checked. "
                             f"The Table has {wip_oal} fields marked with oal")

    def validate_restriction_rules(self, table_name):
        if self.get(table_name):
            for d in self.get(table_name):
                if d.item_number == 0:
                    d.item_number = 1
                d.is_numeric = frappe.get_value("Item Attribute", d.attribute, "numeric_values")
                if d.is_numeric == 1:
                    d.allowed_values = ""
                else:
                    att_doc = frappe.get_doc("Item Attribute", d.attribute)
                    check_text_attributes(att_doc=att_doc, att_value=d.allowed_values, error=0)
                    d.rule = ""

    def validate_operations(self):
        for d in self.operations:
            op_doc = frappe.get_doc("Operation", d.operation)
            if op_doc.is_subcontracting == 1:
                if d.idx == 1:
                    frappe.throw("First Operation Cannot be Sub-Contracting")
                if d.allow_consumption_of_rm == 1:
                    frappe.throw("Sub-Contracting Operation cannot consume Raw Material for Row# {}".format(d.idx))
                if d.idx == len(self.operations):
                    frappe.throw("Sub-Contracting Operation cannot be Last Operation.")

    def generate_title(self):
        title = ""
        rule = 0
        for d in self.fg_restrictions:
            if d.is_numeric != 1:
                desc = get_desc(d.attribute, d.allowed_values)
                if d.idx == 1:
                    title += desc
                else:
                    title += " " + desc
            else:
                if rule == 0:
                    title += ", Rules For: " + d.attribute
                    rule = 1
                else:
                    title += ", " + d.attribute
        self.title = title
