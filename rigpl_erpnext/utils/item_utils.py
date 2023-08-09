# -*- coding: utf-8 -*-
# Copyright (c) 2019, Rohit Industries Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import datetime
import re

import frappe
from frappe import scrub
from frappe.utils import flt


def delete_web_item(item_code):
    """
    Deletes the Website Item for an Item Code if it exists
    """
    wb_it = frappe.get_doc("Website Item", {"item_code": item_code})
    if wb_it:
        frappe.delete_doc(wb_it.doctype, wb_it.name, delete_permanently=True)


def get_pricing_rule_for_item(it_name, frm_dt=None, to_dt=None):
    cond = f" AND pri.item_code = '{it_name}'"
    if frm_dt:
        cond += f" AND pr.valid_from <= '{frm_dt}'"
    if to_dt:
        cond += f" AND pr.valid_upto >= '{to_dt}'"
    query = f"""SELECT pr.name, pr.min_qty, pr.min_amt, pr.max_qty, pr.max_amt, pr.currency,
    pr.rate, pr.valid_from, pr.valid_upto
    FROM `tabPricing Rule` pr, `tabPricing Rule Item Code` pri
    WHERE pri.parent = pr.name AND pr.apply_on = 'Item Code' AND (pr.applicable_for IS NULL
    OR pr.applicable_for = '') {cond} ORDER BY pr.valid_upto, pr.min_qty"""
    pr_dict = frappe.db.sql(query, as_dict=1)
    if pr_dict:
        return pr_dict
    else:
        return []


def get_distinct_attributes(item_dict, field_name):
    att_dict = frappe.db.sql(
        """SELECT DISTINCT(iva.attribute) as att_name,
        ia.short_name as att_sn
        FROM `tabItem Variant Attribute` iva, `tabItem Attribute` ia
        WHERE ia.name = iva.attribute AND iva.parent in (%s)
        ORDER BY iva.idx"""
        % (", ".join(["%s"] * len(item_dict))),
        tuple([d.get(field_name) for d in item_dict]),
        as_dict=1,
    )
    return att_dict


def check_and_copy_attributes_to_variant(template, variant, insert_type=None):
    from frappe.model import no_value_fields

    check = 0
    save_chk = 0
    copy_field_list = frappe.db.sql(
        """SELECT field_name FROM `tabVariant Field`""", as_list=1
    )
    include_fields = []
    for fields in copy_field_list:
        include_fields.append(fields[0])
    for field in template.meta.fields:
        if (
            field.fieldtype not in no_value_fields
            and (not field.no_copy)
            and field.fieldname in include_fields
        ):
            if variant.get(field.fieldname) != template.get(field.fieldname):
                if insert_type == "frontend":
                    variant.set(field.fieldname, template.get(field.fieldname))
                    frappe.msgprint(
                        "Updated Item "
                        + variant.name
                        + " Field Changed = "
                        + str(field.label)
                        + " Updated Value to "
                        + str(template.get(field.fieldname))
                    )
                else:
                    frappe.db.set_value(
                        "Item",
                        variant.name,
                        field.fieldname,
                        template.get(field.fieldname),
                    )
                    print(
                        "Updated Item "
                        + variant.name
                        + " Field Changed = "
                        + str(field.label)
                        + " Updated Value to "
                        + str(template.get(field.fieldname))
                    )
                check += 1
        elif field.fieldname == "description":
            description, long_desc = generate_description(variant)
            if variant.get(field.fieldname) != description:
                if insert_type == "frontend":
                    variant.set(field.fieldname, template.get(field.fieldname))
                else:
                    frappe.db.set_value(
                        "Item", variant.name, field.fieldname, description
                    )
                    frappe.db.set_value(
                        "Item", variant.name, "web_long_description", long_desc
                    )
                    frappe.db.set_value("Item", variant.name, "item_name", long_desc)
                    print(
                        "Updated Item "
                        + variant.name
                        + " Field Changed = "
                        + str(field.label)
                        + " Updated Value to "
                        + description
                    )
        if insert_type != "frontend":
            frappe.db.set_value(
                "Item", variant.name, "modified", datetime.datetime.now()
            )
    return check


def web_catalog(it_doc):
    validate_stock_fields(it_doc)
    validate_restriction(it_doc)
    validate_item_defaults(it_doc)
    it_doc.website_image = it_doc.image
    it_doc.thumbnail = it_doc.image
    if it_doc.pl_item == "Yes":
        it_doc.show_in_website = 1
        if it_doc.has_variants == 0:
            it_doc.show_variant_in_website = 1
        else:
            it_doc.show_variant_in_website = 0
    else:
        it_doc.show_in_website = 0
        it_doc.show_variant_in_website = 0

    if it_doc.show_in_website == 1:
        rol = frappe.db.sql(
            """SELECT warehouse_reorder_level
        FROM `tabItem Reorder` WHERE parent ='%s' """
            % (it_doc.name),
            as_list=1,
        )
        if it_doc.item_defaults:
            for d in it_doc.item_defaults:
                it_doc.website_warehouse = d.default_warehouse
        if rol:
            it_doc.weightage = rol[0][0]


def validate_attribute_numeric(it_doc):
    for d in it_doc.attributes:
        d.numeric_values = frappe.get_value(
            "Item Attribute", d.attribute, "numeric_values"
        )


def validate_restriction(it_doc):
    if it_doc.has_variants == 1:
        # Check if the Restrictions Numeric check field is correctly selected
        for d in it_doc.item_variant_restrictions:
            if d.is_numeric == 1:
                if d.allowed_values:
                    frappe.throw(
                        "Allowed Values field not allowed for numeric attribute {0}".format(
                            d.attribute
                        )
                    )
            elif d.is_numeric == 0:
                if d.rule:
                    frappe.throw(
                        "Rule not allowed for non-numeric attribute {0}".format(
                            d.attribute
                        )
                    )


def validate_item_defaults(it_doc):
    if it_doc.item_defaults:
        if len(it_doc.item_defaults) > 1:
            frappe.throw("Currently Only one line of defaults are supported")
        for d in it_doc.item_defaults:
            if d.default_warehouse:
                def_warehouse = d.default_warehouse
            else:
                frappe.throw(
                    "Default Warehouse is Mandatory for Item Code: {}".format(
                        it_doc.name
                    )
                )
            if d.default_price_list:
                def_price_list = d.default_price_list
            else:
                if it_doc.is_sales_item == 1:
                    frappe.throw(
                        "Default Price List is Mandatory for Item Code: {}".format(
                            it_doc.name
                        )
                    )


def generate_description(it_doc):
    if it_doc.variant_of:
        desc = []
        description = ""
        long_desc = ""
        for d in it_doc.attributes:
            concat = ""
            concat1 = ""
            concat2 = ""
            is_numeric = frappe.db.get_value(
                "Item Attribute", d.attribute, "numeric_values"
            )
            use_in_description = frappe.db.sql(
                """SELECT iva.use_in_description from `tabItem Variant Attribute` iva
            WHERE iva.parent = '%s' AND iva.attribute = '%s' """
                % (it_doc.variant_of, d.attribute),
                as_list=1,
            )[0][0]

            if is_numeric != 1 and use_in_description == 1:
                # Below query gets the values of description mentioned in the Attribute table
                # for non-numeric values
                cond1 = d.attribute
                cond2 = d.attribute_value
                query = """SELECT iav.description AS descrip, iav.long_description AS lng_desc
                FROM `tabItem Attribute Value` iav, `tabItem Attribute` ia
                WHERE iav.parent = '%s' AND iav.parent = ia.name
                AND iav.attribute_value = '%s'""" % (
                    cond1,
                    cond2,
                )
                vatt_lst = frappe.db.sql(query, as_dict=1)
                if not vatt_lst:
                    frappe.throw(
                        f"No Value found for Attribute {d.attribute} bearing Value {d.attribute_value}"
                    )
                prefix = frappe.db.sql(
                    """SELECT iva.prefix AS pref FROM `tabItem Variant Attribute` iva
                WHERE iva.parent = '%s' AND iva.attribute = '%s' """
                    % (it_doc.variant_of, d.attribute),
                    as_dict=1,
                )
                suffix = frappe.db.sql(
                    """SELECT iva.suffix AS suffix FROM `tabItem Variant Attribute` iva
                WHERE iva.parent = '%s' AND iva.attribute = '%s' """
                    % (it_doc.variant_of, d.attribute),
                    as_dict=1,
                )
                concat = ""
                concat2 = ""
                if prefix[0].pref != '""':
                    if vatt_lst[0].descrip:
                        concat1 = str(prefix[0].pref[1:-1]) + str(
                            vatt_lst[0].descrip[1:-1]
                        )
                    if vatt_lst[0].lng_desc:
                        concat2 = str(prefix[0].pref[1:-1]) + str(
                            vatt_lst[0].lng_desc[1:-1]
                        )
                else:
                    if vatt_lst and vatt_lst[0].descrip != '""':
                        concat1 = str(vatt_lst[0].descrip[1:-1])
                    if vatt_lst and vatt_lst[0].lng_desc != '""':
                        concat2 = str(vatt_lst[0].lng_desc[1:-1])

                if suffix[0].suffix != '""':
                    concat1 = concat1 + str(suffix[0].suffix[1:-1])
                    concat2 = concat2 + str(suffix[0].suffix[1:-1])
                desc.extend([[concat1, concat2, d.idx]])

            elif is_numeric == 1 and use_in_description == 1:
                concat = ""
                concat2 = ""
                # Below query gets the values of description mentioned in the Attribute table
                # for Numeric values
                query1 = (
                    """SELECT iva.idx FROM `tabItem Variant Attribute` iva
                WHERE iva.attribute = '%s'"""
                    % d.attribute
                )

                prefix = frappe.db.sql(
                    """SELECT iva.prefix FROM `tabItem Variant Attribute` iva
                WHERE iva.parent = '%s' AND iva.attribute = '%s' """
                    % (it_doc.variant_of, d.attribute),
                    as_list=1,
                )

                suffix = frappe.db.sql(
                    """SELECT iva.suffix FROM `tabItem Variant Attribute` iva
                WHERE iva.parent = '%s' AND iva.attribute = '%s' """
                    % (it_doc.variant_of, d.attribute),
                    as_list=1,
                )

                concat = ""
                if prefix[0][0] != '""':
                    if flt(d.attribute_value) > 0:
                        concat = str(prefix[0][0][1:-1]) + str(
                            "{0:g}".format(flt(d.attribute_value))
                        )
                else:
                    if flt(d.attribute_value) > 0:
                        concat = str("{0:g}".format(flt(d.attribute_value)))

                if suffix[0][0] != '""':
                    if concat:
                        concat = concat + str(suffix[0][0][1:-1])
                desc.extend([[concat, concat, d.idx]])

            else:
                query1 = (
                    """SELECT iva.idx FROM `tabItem Variant Attribute` iva
                WHERE iva.attribute = '%s'"""
                    % d.attribute
                )
                desc.extend([["", "", frappe.db.sql(query1, as_list=1)[0][0]]])

        desc.sort(
            key=lambda x: x[2]
        )  # Sort the desc as per priority lowest one is taken first
        for i in range(len(desc)):
            if desc[i][0] != '""':
                description = description + desc[i][0]
            if desc[i][1] != '""':
                long_desc = long_desc + desc[i][1]
    else:
        description = it_doc.name
        long_desc = it_doc.name
    return description, long_desc


def make_route(it_doc):
    route_name = re.sub("[^A-Za-z0-9]+", " ", it_doc.item_name)
    if it_doc.has_variants == 1:
        it_doc.route = (
            frappe.db.get_value("Item Group", it_doc.item_group, "route")
            + "/"
            + scrub(it_doc.route_name)
        )
    else:
        if it_doc.variant_of:
            it_doc.route = (
                frappe.db.get_value("Item", it_doc.variant_of, "route")
                + "/"
                + scrub(it_doc.route_name)
            )


def validate_reoder(it_doc):
    for val in it_doc.item_defaults:
        def_warehouse = val.default_warehouse
    for d in it_doc.reorder_levels:
        if d.warehouse != def_warehouse:
            d.warehouse = def_warehouse
    validate_valuation_rate(it_doc)


def validate_valuation_rate(it_doc):
    if it_doc.has_variants == 1 and it_doc.is_sales_item == 1:
        if it_doc.valuation_as_percent_of_default_selling_price == 0:
            frappe.throw("Valuation Rate Percent cannot be ZERO")


def validate_variants(it_doc, comm_type=None):
    user = frappe.session.user
    query = """SELECT role from `tabHas Role` where parent = '%s' """ % user
    roles = frappe.db.sql(query, as_list=1)

    if it_doc.published_in_website == 1:
        if it_doc.image is None:
            frappe.throw(
                f"For Website Items, Website Image is Mandatory for Item Code {it_doc.name}"
            )
    if it_doc.variant_of:
        # Check if all variants are mentioned in the Item Variant Table as per the Template.
        template = frappe.get_doc("Item", it_doc.variant_of)
        check_item_defaults(template, it_doc, comm_type)
        template_attribute = []
        variant_attribute = []
        template_restricted_attributes = {}
        template_rest_summary = []

        for t in template.attributes:
            template_attribute.append(t.attribute)

        count = 0
        for d in it_doc.attributes:
            variant_attribute.append([d.attribute])
            variant_attribute[count].append(d.attribute_value)
            count += 1

        # First check the order of all the variants is as per the template or not.
        for i in range(len(template_attribute)):
            if (
                len(template_attribute) == len(variant_attribute)
                and template_attribute[i] != variant_attribute[i][0]
            ):
                frappe.throw(
                    "Item Code: {0} Row# {1} should have {2} as per the template".format(
                        it_doc.name, i + 1, template_attribute[i]
                    )
                )

            elif len(template_attribute) != len(variant_attribute):
                frappe.throw(
                    "Item Code: {0} number of attributes not as per the template".format(
                        it_doc.name
                    )
                )

        # Now check the values of the Variant and if they are within the restrictions.
        # 1. Check if the Select field is as per restriction table
        # 2. Check the rule of the numeric fields like d1_mm < d2_mm

        for t in template.item_variant_restrictions:
            template_rest_summary.append(t.attribute)
            template_restricted_attributes.setdefault(
                t.attribute, {"rules": [], "allows": []}
            )
            if t.is_numeric == 1:
                template_restricted_attributes[t.attribute]["rules"].append(t.rule)
            else:
                template_restricted_attributes[t.attribute]["allows"].append(
                    t.allowed_values
                )

        ctx = {}
        for d in it_doc.attributes:
            is_numeric = frappe.db.get_value(
                "Item Attribute", d.attribute, "numeric_values"
            )
            """
            # Below code was un-necessarily changing the Attribute Value basically not changing but showing
            # in Versioning
            if is_numeric == 1:
                d.attribute_value = flt(d.attribute_value)
            """
            ctx[d.attribute] = flt(d.attribute_value)

        original_keys = ctx.keys()

        for d in it_doc.attributes:
            chk_numeric = frappe.db.get_value(
                "Item Attribute", d.attribute, "numeric_values"
            )

            if chk_numeric == 1:
                if template_restricted_attributes.get(d.attribute):
                    rules = template_restricted_attributes.get(d.attribute, {}).get(
                        "rules", []
                    )
                    for rule in rules:
                        repls = {
                            "!": " not ",
                            "false": "False",
                            "true": "True",
                            "&&": " and ",
                            "||": " or ",
                            "&gt;": ">",
                            "&lt;": "<",
                        }
                        for k, v in repls.items():
                            rule = rule.replace(k, v)
                        try:
                            valid = eval(rule, ctx, ctx)
                        except Exception as e:
                            frappe.throw(
                                "\n\n".join(
                                    map(
                                        str,
                                        [
                                            rule,
                                            {
                                                k: v
                                                for k, v in ctx.items()
                                                if k in original_keys
                                            },
                                            e,
                                        ],
                                    )
                                )
                            )

                        if not valid:
                            frappe.throw(
                                'Item Code: {0} Rule "{1}" failing for field "{2}"'.format(
                                    it_doc.name, rule, d.attribute
                                )
                            )
            else:
                if template_restricted_attributes.get(d.attribute, {}).get(
                    "allows", False
                ):
                    if d.attribute_value not in template_restricted_attributes.get(
                        d.attribute, {}
                    ).get("allows", []):
                        frappe.throw(
                            "Item Code: {0} Attribute value {1} not allowed".format(
                                it_doc.name, d.attribute_value
                            )
                        )

        # Check the limit in the Template
        limit = template.variant_limit
        actual = frappe.db.sql(
            """SELECT count(name) FROM `tabItem` WHERE variant_of = '%s'"""
            % template.name,
            as_list=1,
        )

        check = frappe.db.sql(
            """SELECT name FROM `tabItem` WHERE name = '%s'""" % it_doc.name, as_list=1
        )

        if check:
            if actual[0][0] > limit:
                frappe.throw(
                    (
                        "Template Limit reached. Set Limit = {0} whereas total number of variants = {1} "
                        "increase the limit to save the variant"
                    ).format(limit, actual[0][0])
                )
            else:
                pass
        else:
            if actual[0][0] >= limit:
                frappe.throw(
                    (
                        "Template Limit reached. Set Limit = {0} whereas total number of variants = {1} "
                        "increase the limit to save New Item Code"
                    ).format(limit, actual[0][0])
                )
    elif it_doc.has_variants != 1:
        if any("System Manager" in s for s in roles):
            pass
        else:
            frappe.throw(
                "Only System Managers are Allowed to Create Non Template or Variant Items"
            )
    elif it_doc.has_variants == 1:
        if any("System Manager" in s for s in roles):
            pass
        else:
            frappe.throw("Only System Managers are Allowed to Edit Templates")


def check_item_defaults(template, variant, comm_type=None):
    field_list = [
        "company",
        "default_warehouse",
        "default_price_list",
        "income_account",
        "buying_cost_center",
        "selling_cost_center",
    ]
    if template.item_defaults:
        # Check if Item Defaults exists in the Template
        t_def = 1
    else:
        t_def = 0

    if variant.item_defaults:
        # Check if Item Defaults exists in the Template
        v_def = 1
    else:
        v_def = 0

    if t_def == 1:
        if v_def == 1:
            is_it_def_same = compare_item_defaults(
                template, variant, field_list, comm_type
            )
            if is_it_def_same == 1:
                pass
            else:
                copy_item_defaults(template, variant, field_list, comm_type)
    # condition when template defaults are there then copy them
    else:
        frappe.throw(
            "Item Defaults are Mandatory for Template {}".format(template.name)
        )


def compare_item_defaults(template, variant, field_list, comm_type=None):
    i = 0
    for t in template.item_defaults:
        for v in variant.item_defaults:
            for f in field_list:
                if t.get(f) == v.get(f):
                    i += 1
    if len(field_list) == i:
        # All fields are same so return 1 meaning item defaults are Same
        return 1
    else:
        return 0


def copy_item_defaults(template, variant, field_list, comm_type=None):
    variant.item_defaults = []
    variant_defaults = []
    var_def_dict = {}
    for t in template.item_defaults:
        for f in field_list:
            var_def_dict[f] = t.get(f)
        variant_defaults.append(var_def_dict)
    for i in variant_defaults:
        variant.append("item_defaults", i)
    if comm_type == "backend":
        it_def_name = frappe.db.sql(
            """SELECT name FROM `tabItem Default` WHERE parent= '%s' AND parenttype='Item'"""
            % (variant.name),
            as_list=1,
        )
        if it_def_name:
            for t in template.item_defaults:
                for f in field_list:
                    frappe.db.set_value("Item Default", it_def_name[0][0], f, t.get(f))
                    frappe.db.set_value(
                        "Item", variant.name, "modified", datetime.datetime.now()
                    )


def validate_stock_fields(it_doc):
    # As per Company Policy on FIFO method of Valuation is to be Used.
    if it_doc.is_stock_item == 1:
        if it_doc.valuation_method != "FIFO":
            frappe.throw("Select Valuation method as FIFO for Stock Item")
    if it_doc.is_purchase_item == 1:
        it_doc.default_material_request_type = "Purchase"
    else:
        it_doc.default_material_request_type = "Manufacture"


def validate_sales_fields(it_doc):
    if it_doc.is_sales_item == 1:
        if it_doc.sales_uom:
            pass
        else:
            frappe.throw("Sales UoM is Mandatory for Sales Item")
    if it_doc.pack_size == 0:
        frappe.throw("Pack Size should be Greater Than ZERO")
    if it_doc.selling_mov == 0:
        frappe.throw("Selling Minimum Order Value should be Greater than ZERO")


def get_desc(attribute, attribute_value):
    desc = frappe.db.sql(
        """SELECT description FROM `tabItem Attribute Value` WHERE parent = '%s' AND parenttype =
    'Item Attribute' AND attribute_value = '%s'
    AND parentfield = 'item_attribute_values'"""
        % (attribute, attribute_value),
        as_dict=1,
    )
    if desc:
        desc = desc[0].description[1:-1]
    return desc


def check_numeric_attributes(att_doc, att_value, deny=1):
    try:
        val = float(att_value)
        if att_doc.from_range < flt(att_value) < att_doc.to_range:
            pass
        else:
            frappe.msgprint(str(flt(att_value)))
            range_message = "Allowed Values for {} should be between {} and {}".format(
                att_doc.name, att_doc.from_range, att_doc.to_range
            )
            if deny == 1:
                frappe.throw(range_message)
            else:
                frappe.msgprint(range_message)
    except ValueError:
        non_numeric_message = (
            "{} entered for {} is not numeric value hence not allowed".format(
                att_value, att_doc.name
            )
        )
        frappe.throw(non_numeric_message)


def check_text_attributes(att_doc, att_value, error=1):
    if att_doc.item_attribute_values:
        found = 0
        allowed_values = []
        for d in att_doc.item_attribute_values:
            if d.attribute_value == att_value:
                found = 1
                break
            else:
                allowed_values.append(d.attribute_value)
        if found != 1:
            not_found = "{} entered is not allowed. Allowed Values are {}".format(
                att_value, str(allowed_values)
            )
            if error == 1:
                frappe.throw(not_found)
            else:
                frappe.msgprint(not_found)
    else:
        frappe.throw(
            "For {} No Attribute Values are Defined".format(
                frappe.get_desk_link(att_doc.doctype, att_doc.name)
            )
        )


def get_template_restrictions(temp_name):
    """
    Returns a dictionary for Template with Item Restrictions
    """
    temp_dict = frappe.db.sql(
        """SELECT name, idx, attribute, is_numeric, allowed_values, rule
        FROM `tabItem Variant Restrictions` WHERE parenttype = 'Item'
        AND parent = '%s' ORDER BY idx"""
        % temp_name,
        as_dict=1,
    )
    return temp_dict


def get_item_attributes(item_name):
    """
    Returns a dictionary for all Attributes for an Item Name
    """
    att_dict = frappe.db.sql(
        """SELECT name, idx, attribute, attribute_value, prefix,
        use_in_description, field_name, from_range, to_range, increment, numeric_values
        FROM `tabItem Variant Attribute` WHERE parenttype = 'Item'
        AND parent = '%s' ORDER BY idx"""
        % item_name,
        as_dict=1,
    )
    return att_dict
