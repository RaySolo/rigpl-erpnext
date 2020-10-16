# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import re
import frappe
from frappe.utils import flt
from ..utils.manufacturing_utils import replace_java_chars


def check_validated_gstin(add_name):
    add_doc = frappe.get_doc("Address", add_name)
    if add_doc.gstin:
        if add_doc.gstin != "NA":
            if add_doc.validated_gstin != add_doc.gstin:
                frappe.throw("GSTIN# {} for {} is NOT Validated from GST Website. Please update the "
                             "Address from GST Website".
                             format(add_doc.gstin, frappe.get_desk_link(add_doc.doctype, add_doc.name)))


def dead_stock_order_booking(doc):
    """Validation to Disallow Booking of Orders for More than Available Quantity for Items in Dead Stock"""
    for it in doc.items:
        qty_dict = frappe.db.sql("""SELECT bn.warehouse, bn.reserved_qty, bn.actual_qty, bn.reserved_qty_for_production,
            wh.warehouse_type
            FROM `tabBin` bn, `tabWarehouse` wh
            WHERE bn.warehouse = wh.name AND wh.disabled =0 AND bn.item_code = '%s'"""% it.item_code, as_dict=1)
        frappe.msgprint(str(qty_dict))
        check_dead = 0
        for wh in qty_dict:
            if wh.warehouse_type == 'Dead Stock' and wh.actual_qty > 0:
                check_dead = 1
        if check_dead == 1:
            tot_actual_qty = 0
            tot_reserved_qty = 0
            tot_reserved_qty_for_production = 0
            for wh in qty_dict:
                if wh.warehouse_type in ('Finished Stock', 'Dead Stock'):
                    tot_actual_qty += wh.actual_qty
                    tot_reserved_qty += wh.reserved_qty
                    tot_reserved_qty_for_production += wh.reserved_qty_for_production
            allowed_so_qty = tot_actual_qty - tot_reserved_qty - tot_reserved_qty_for_production
            if it.qty > allowed_so_qty:
                frappe.throw('Row# {}, {} is in Dead Stock and Allowed Qty for SO Booking = {}'.
                             format(it.idx, frappe.get_desk_link('Item', it.item_code), allowed_so_qty))


def validate_made_to_order_items(doc):
    '''
    This validation basically checks if an Item is Made to Order or Not if Item is Made to Order or Special Item
    Then the system would check if all the Process Sheet Job Cards are completed or Not.
    '''
    for it in doc.items:
        made_to_order = frappe.get_value('Item', it.item_code, 'made_to_order')
        if made_to_order == 1 and doc.bypass_made_to_order_check != 1:
            # Check if the Item as per the Process Sheet or Not
            validate_special_items(doc, it)
            validate_warehouse(doc, it)
        elif doc.bypass_made_to_order_check != 1:
            validate_warehouse(doc, it)


def validate_special_items(doc, row):
    pro_sheet = frappe.db.sql("""SELECT name FROM `tabProcess Sheet` WHERE production_item = '%s' 
        AND sales_order_item = '%s' AND docstatus = 1""" %(row.item_code, row.so_detail), as_list=1)
    if not pro_sheet:
        frappe.throw("There is No Processing Done for {} in Row# {} for {}".
                     format(row.item_code, row.idx, frappe.get_desk_link(doc.doctype, doc.name)))
    else:
        # If there is a Submitted Process Sheet then Check if all the Job Cards are Submitted for the Same Quantity
        ps_doc = frappe.get_doc('Process Sheet', pro_sheet[0][0])
        for d in ps_doc.operations:
            if d.final_operation == 1:
                jc_list = frappe.db.sql("""SELECT name FROM `tabProcess Job Card RIGPL` WHERE docstatus !=2 
                    AND operation_id = '%s'"""%(d.name), as_list=1)
                if not jc_list:
                    frappe.throw('There is No Job Card for {} final operation'.format(frappe.get_desk_link(
                        doc.doctype, doc.name)))
                else:
                    jc_doc = frappe.get_doc('Process Job Card RIGPL', jc_list[0][0])
                    if jc_doc.docstatus != 1:
                        frappe.throw("For Row# {} in {}, the Final Process is Not Completed in {}".
                                     format(row.idx, frappe.get_desk_link(doc.doctype, doc.name),
                                            frappe.get_desk_link('Process Job Card RIGPL', jc_doc.name)))
                    else:
                        frappe.throw("HELLO")


def validate_warehouse(doc, row):
    """Only Allow from Finished Stock Warehouse"""
    wh_doc = frappe.get_doc('Warehouse', row.warehouse)
    if wh_doc.warehouse_type != 'Finished Stock':
        frappe.throw("In {}, Row# {} and {} the {} selected is Not Finished Stock Warehouse".
            format(frappe.get_desk_link(doc.doctype, doc.name), row.idx, frappe.get_desk_link('Item', row.item_code),
                   frappe.get_desk_link('Warehouse', row.warehouse)))
    elif wh_doc.disabled == 1:
        frappe.throw("In {}, Row# {} and {} the {} selected is Disabled Warehouse".
            format(frappe.get_desk_link(doc.doctype, doc.name), row.idx, frappe.get_desk_link('Item', row.item_code),
                   frappe.get_desk_link('Warehouse', row.warehouse)))


def validate_address_google_update(add_doc_name):
    add_doc = frappe.get_doc('Address', add_doc_name)
    if not add_doc.json_reply and add_doc.dont_update_from_google != 1:
        frappe.throw('Address {} is Not Updated from Google, Please Open and Save '
                     'the Address once'.format(add_doc.name))


def copy_address_and_check(document):
    if document.doctype == 'Delivery Note':
        so_field = "against_sales_order"
    elif document.doctype == 'Sales Invoice':
        so_field = 'sales_order'
    for items in document.items:
        if items.get(so_field):
            so_doc = frappe.get_doc("Sales Order", items.get(so_field))
            if document.customer_address != so_doc.customer_address:
                frappe.throw("Customer Address mentioned in {} {} does not match with Customer Address of SO# {} "
                             "mentioned in Row# {}".format(document.doctype, document.name, items.get(so_field),
                                                           items.idx))
            if document.shipping_address_name != so_doc.shipping_address_name:
                frappe.throw("Shipping Address mentioned in {} {} does not match with Shipping Address of SO# {} "
                             "mentioned in Row# {}".format(document.doctype, document.name, items.get(so_field),
                                                           items.idx))


def check_strict_po_rules(document):
    follow_rules = 0
    cust_rule = 0
    so_rule = 0
    so_list = []
    if document.doctype == 'Delivery Note':
        so_field = "against_sales_order"
    elif document.doctype == 'Sales Invoice':
        so_field = 'sales_order'
    cust_doc = frappe.get_doc("Customer", document.customer)

    if cust_doc.follow_strict_po_rules == 1:
        follow_rules = 1
        cust_rule = 1

    for it in document.items:
        if it.get(so_field):
            so_doc = frappe.get_doc('Sales Order', it.get(so_field))
            if so_doc.follow_strict_po_rules == 1:
                follow_rules = 1
                so_rule = 1
            if it.idx == 1:
                so_list.append(it.get(so_field))
            elif it.idx > 1 and follow_rules == 1:
                frappe.throw("{} Follows Strict PO Rules for {} hence Row {} is Rejected. Make new {} "
                             "for SO# {}".
                             format(frappe.get_desk_link("Customer", document.customer),
                                frappe.get_desk_link("Sales Order", it.get(so_field)), it.idx, document.doctype,
                                frappe.get_desk_link("Sales Order", it.get(so_field))))
                if it.get(so_field) not in so_list:
                    pass


def get_hsn_code(row_dict):
    custom_tariff = frappe.db.get_value("Item", row_dict.item_code, "customs_tariff_number")
    if custom_tariff:
        if len(custom_tariff) == 8:
            row_dict.gst_hsn_code = custom_tariff
        else:
            frappe.throw(("Item Code {0} in line# {1} has a Custom Tariff {2} which not  8 digit, please get the "
                          "Custom Tariff corrected").format(row_dict.item_code, row_dict.idx, custom_tariff))
    else:
        frappe.throw("Item Code {0} in line# {1} does not have linked Customs Tariff in Item Master".format(
            row_dict.item_code, row_dict.idx))


def check_get_pl_rate(document, row_dict):
    pl_doc = frappe.get_doc("Price List", row_dict.price_list)
    if pl_doc.disable_so == 1:
        frappe.throw("Sales Order Booking Disabled for {} at Row# {}".format(row_dict.price_list, row_dict.idx))
    item_pl_rate = frappe.db.sql("""SELECT price_list_rate, currency FROM `tabItem Price`
            WHERE price_list = '%s' AND item_code = '%s' 
            AND selling = 1""" % (row_dict.price_list, row_dict.item_code), as_dict=1)

    if item_pl_rate:
        if row_dict.price_list_rate != item_pl_rate[0].price_list_rate and document.currency == item_pl_rate[0].currency:
            row_dict.price_list_rate = item_pl_rate[0].price_list_rate
    else:
        frappe.msgprint("In {}# {} at Row# {} and Item Code: {} Price List Rate is Not Defined".format(
            document.doctype, document.name, row_dict.idx, row_dict.item_code))


def check_dynamic_link(parenttype, parent, link_doctype, link_name):
    link_type = frappe.db.sql("""SELECT name FROM `tabDynamic Link` 
        WHERE docstatus = 0 AND parenttype = '%s' AND parent = '%s'
        AND link_doctype = '%s' AND link_name = '%s'""" % (parenttype, parent, link_doctype, link_name), as_list=1)
    if not link_type:
        frappe.throw("{} {} does not belong to {} {}".format(parenttype, parent, link_doctype, link_name))


def check_taxes_integrity(document):
    template = frappe.get_doc("Sales Taxes and Charges Template", document.taxes_and_charges)
    if len(template.taxes) != len(document.taxes):
        frappe.throw("Tax Template {} Data does not match with Document# {}'s Tax {}".
                     format(template.name,document.name, document.taxes_and_charges))
    for tax in document.taxes:
        for temp in template.taxes:
            if tax.idx == temp.idx:
                if tax.charge_type != temp.charge_type or tax.row_id != temp.row_id or tax.account_head != \
                        temp.account_head or tax.included_in_print_rate != temp.included_in_print_rate or tax.rate !=\
                        temp.rate:
                    frappe.throw(("Selected Tax {0}'s table does not match with tax table of Sales Order# {1}. Check "
                                  "Row # {2} or reload Taxes").format(document.taxes_and_charges, document.name,
                                                                      tax.idx))


def check_gst_rules(doc, bill_add_name, taxes_name):
    bill_add_doc = frappe.get_doc("Address", bill_add_name)
    template_doc = frappe.get_doc("Sales Taxes and Charges Template", taxes_name)

    bill_state = bill_add_doc.state_rigpl
    bill_country = bill_add_doc.country

    # Check series of Tax with the Series Selected for Invoice
    series_regex = replace_java_chars(template_doc.series)
    if series_regex:
        if 'or' in series_regex:
            ser_regex = series_regex.split("or")
        else:
            ser_regex = [series_regex]
        series_regex_pass = 0
        for d in ser_regex:
            p = re.compile(d.strip())
            if not p.match(doc.name):
                pass
            else:
                series_regex_pass = 1
        if series_regex_pass != 1:
            frappe.throw("{}: is not as per the defined Series in {}".
                         format(doc.name, frappe.get_desk_link(template_doc.doctype, template_doc.name)))
    else:
        frappe.throw("Series Regex Not Defined for {} and {}".
                     format(frappe.get_desk_link(doc.doctype, doc.name),
                            frappe.get_desk_link(template_doc.doctype, template_doc.name)))

    if taxes_name != 'OGL':
        # Check if Shipping State is Same as Template State then check if the tax template is LOCAL
        # Else if the States are different then the template should NOT BE LOCAL
        if bill_state == template_doc.state and template_doc.is_export != 1:
            if template_doc.is_local_sales != 1:
                frappe.throw(("Selected Tax {0} is NOT LOCAL Tax but Shipping Address is in Same State {1}, "
                              "hence either change Shipping Address or Change the Selected Tax").format(taxes_name,
                                                                                                        bill_state))
        elif bill_country == 'India' and bill_state != template_doc.state:
            if template_doc.is_local_sales == 1:
                frappe.throw(("Selected Tax {0} is LOCAL Tax but Shipping Address is in Different State {1}, "
                              "hence either change Shipping Address or Change the Selected Tax").format(taxes_name,
                                                                                                        bill_state))
        elif bill_country != 'India':  # Case of EXPORTS
            if template_doc.state is not None and template_doc.is_export != 1:
                frappe.throw("Selected Tax {0} is for Indian Sales but Shipping Address is in Different Country {1}, "
                             "hence either change Shipping Address or Change the Selected Tax".format(taxes_name,
                                                                                                      bill_country))


@frappe.whitelist()
def get_pending_so_with_items(doctype, txt, searchfield, start, page_len, filters):
    return frappe.db.sql("""SELECT so.name, so.customer, soi.item_code, soi.description, soi.qty,
        soi.delivered_qty, soi.name FROM `tabSales Order` so, `tabSales Order Item` soi WHERE so.docstatus = 1 AND 
        soi.parent = so.name AND so.status != "Closed" AND soi.qty > soi.delivered_qty AND (so.name like %(txt)s or 
        so.customer like %(txt)s) {get_match_cond(doctype)} ORDER BY  if(locate(%(_txt)s, so.name), 
        locate(%(_txt)s, so.name), 1) LIMIT %(start)s, %(page_len)s""", {'txt': "%%%s%%" % txt,
                                                                         '_txt': txt.replace("%", ""),
                                                                         'start': start,
                                                                         'page_len': page_len, })
