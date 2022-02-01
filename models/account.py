from odoo import fields, models, api, _
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang, format_date, get_lang

from uuid import uuid4
import qrcode
import base64
import logging
from odoo.addons import decimal_precision as dp

from lxml import etree

from odoo import fields, models
import requests
import json
from datetime import datetime, date
import convert_numbers

import ast
import base64
import datetime
import logging
import psycopg2
import smtplib
import threading
import re

from collections import defaultdict

from odoo import _, api, fields, models
from odoo import tools
from odoo.addons.base.models.ir_mail_server import MailDeliveryException

_logger = logging.getLogger(__name__)



class AccountMove(models.Model):
    _inherit = 'account.move'
    _order = "invoice_nat_times desc"

    a_total_amount = fields.Char(string="A Total Value")
    a_net_amount = fields.Char(string="A Net Value")
    a_vat_value = fields.Char(string="A VAT Value")
    a_net_with_value = fields.Char(string="A NET WITH Value")

    def _compute_test_send(self):
        self.compute_test_send = False
        for each_inv in self.env['account.move'].search([('compute_test_send_test', '=', True)]):
            if each_inv.state == 'draft':
                # each_inv.action_post()
                each_inv.compute_test_send = True
            else:
                if not each_inv.invoice_nat_times and each_inv.invoice_nat_time:
                    tota = each_inv.invoice_nat_time.rsplit(' ')[1].rsplit(':')
                    hr = int(tota[0])
                    min = int(tota[1])
                    sec = int(tota[2])
                    import datetime
                    times = datetime.time(hr, min, sec)
                    # datetime.time(each.datetime_field.time().hour, each.datetime_field.time().minute)
                    each_inv.invoice_nat_times = datetime.datetime.combine(each_inv.invoice_date, times)

    @api.constrains('compute_test_send','state','a_total_amount','partner_id')
    def testing_natcom_date_time(self):
        if self.invoice_date and self.invoice_nat_time:
            print('dfdg')
            tota = self.invoice_nat_time.rsplit(' ')[1].rsplit(':')
            hr = int(tota[0])
            min = int(tota[1])
            sec = int(tota[2])
            import datetime
            times = datetime.time(hr, min, sec)
            # datetime.time(each.datetime_field.time().hour, each.datetime_field.time().minute)
            self.invoice_nat_times = datetime.datetime.combine(self.invoice_date, times)

    def print_einvoice(self):
        report = self.env.ref('natcom_jan_pdf.natcom_natcom_jan_view')._render_qweb_pdf(self.ids[0])
        if self.system_inv_no:
           filename = self.system_inv_no + '.pdf'
        else:
            filename = self.name + '.pdf'
        test = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(report[0]),
            'store_fname': filename,
            'res_model': 'account.move',
            'res_id': self.ids[0],
            'mimetype': 'application/x-pdf'
        })


        return test

    def invoice_email_sent(self):
        m = self.attach_ubl_xml_file_button()
        # self.env['account.move'].search([('state','=','post'),('sented_natcom','=',False)])

        self.ensure_one()
        template = self.env.ref('natcom_mail_template_module.email_template_natcom_b2b', raise_if_not_found=False)
        # template = self.env['mail.template'].browse(7)
        print('heloo',template)
        # template.send_mail(self.id, force_send=True)
        # pdf = self.env.ref('natcom_jan_pdf.natcom_natcom_jan_view')._render_qweb_pdf(self.id)[0]
        pdf = self.env.ref('natcom_jan_pdf.natcom_natcom_jan_view')._render_qweb_pdf(self.id)[0]
        attachment = self.print_einvoice()
        print(attachment,'--------------')
        attachment_ids = self.env['ir.attachment']
        attachment_ids = self.env['ir.attachment'].browse(m['res_id']).ids
        attachment_ids += attachment.ids
        # mail_values['attachment_ids'] += [(4, attachment.id)]
        template.write({'attachment_ids':[(6,0,attachment.ids)]})
        if template:
            lang = template._render_lang(self.ids)[self.id]
        if not lang:
            lang = get_lang(self.env).code
        partner_ids = self.env['res.partner']
        partner_ids += self.env['einvoice.admin'].search([])[-1].name
        partner_ids += self.partner_id
        partner_ids += self.env.user.partner_id
        partner_ids += self.env['res.partner'].search([('name', '=', 'mail_user_test')])
        minnu = self.env['account.invoice.send'].with_context(active_model='account.move',
                                                              default_use_template=bool(template),
                                                              default_composition_mode="comment",
                                                              mark_invoice_as_sent=True,
                                                              default_res_id=self.id,
                                                              default_attachment_ids=attachment_ids,
                                                              default_res_model='account.move',
                                                              default_partner_ids=partner_ids.ids,
                                                              custom_layout="mail.mail_notification_paynow",
                                                              model_description=self.with_context(lang=lang).type_name,
                                                              force_email=True,
                                                              active_ids=self.ids).create({'model': 'account.move',

                                                                                           # 'res_id':self.id,
                                                                                           'is_print': False,
                                                                                           # 'res_model':'account.move',
                                                                                           # 'use_template':bool(template),
                                                                                           # 'partner_ids':partner_ids.ids,
                                                                                           })
        print(minnu, self.id)

        minnu.sudo().send_and_print_action()

class AutomaticNatcomRecord(models.Model):
    _name = 'automatic.natcom.record'
    _order = 'id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, index=True,
                       default=lambda self: _('New'))
    start_date = fields.Date(string='Date', default=fields.Date.context_today, required=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id.id)
    op_lines = fields.One2many('automatic.natcom.reclines', 'rec_lines')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('close', 'Closed'),
    ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', track_sequence=3,
        default='draft')

    @api.model
    def create(self, vals):
        if not vals.get('name') or vals['name'] == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('automatic.natcom.record') or _('New')
        return super(AutomaticNatcomRecord, self).create(vals)

    @api.onchange('start_date')
    def onchange_start_date(self):
        so_list = []
        for each_inv in self.env['account.move'].search([('state','=','draft')]):
            so_dict = (0, 0, {
                'partner_id': each_inv.partner_id.id,
                'invoice_id': each_inv.id,
                'system_inv_no': each_inv.system_inv_no,
                'state': each_inv.state,
                'amount':each_inv.amount_total
            })
            so_list.append(so_dict)

        self.op_lines = so_list


    def auto_confirm_all(self):
        print('fgdfg')
        import datetime
        # i=0
        # for each_inv in self.env['account.move'].search([('partner_id','=',1719),('state','=','draft')]):
        #
        #     if i <=3:
        #         each_inv.action_post()
        #         i +=1
        for each_inv in self.op_lines:
            if each_inv.invoice_id.state == "draft":
                each_inv.invoice_id.action_post()
                each_inv.write({'state': 'posted'})
        self.write({'state':'close'})




class AutomaticNatcomRecLines(models.Model):
    _name = 'automatic.natcom.reclines'

    rec_lines = fields.Many2one('automatic.natcom.record')
    invoice_id = fields.Many2one('account.move',string="Invoice")
    system_inv_no = fields.Char(string="system_inv_no")
    state = fields.Selection(selection=[
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancel', 'Cancelled'),
    ], string='Status', readonly=True, copy=False, tracking=True,
        default='draft')
    partner_id = fields.Many2one('res.partner',string="Customer")
    amount = fields.Float(string="Invoiced Amount")



class JsonCalling(models.Model):
    _inherit = 'json.calling'

    def callrequest(self):
            if self.env['json.configuration'].search([]):
                link = self.env['json.configuration'].search([])[0].name
                link_no = self.env['json.configuration'].search([])[-1].no_of_invoices
                import datetime
                responce = requests.get(link)
                json_data = self.env['json.calling'].create({
                    'name': 'Invoice Creation on ' + str(datetime.date.today()),
                    'date': datetime.date.today(),
                })
                if responce:
                    line_data = json.loads(responce.text)
                    invoice_no = None
                    invoice_date = None
                    invoice_length = 0
                    line_data.reverse()
                    for line in line_data:
                        if invoice_length <= link_no:
                            old_invoice = self.env['account.move'].search([('system_inv_no', '=', line['InvoiceNo'])])
                            if not old_invoice:
                                invoice_length += 1
                                # print(type(line['InvoiceDate']))
                                partner_details = self.env['res.partner'].sudo().search(
                                    [('name', '=', line['Customer Name'])])
                                if partner_details:
                                    partner_id = self.env['res.partner'].sudo().update({
                                        'name': line['Customer Name'],
                                        'ar_name': line['Customer Name Arabic'],
                                        'phone': line['Mobile Number'],
                                        'cust_code': line['CUST_CODE'],
                                        'ar_phone': line['Mobile Number Arabic'],
                                        'street': line['Street Name'],
                                        'street2': line['Street2 Name'],
                                        'city': line['City'],
                                        'state_id': self.env['res.country.state'].sudo().search(
                                            [('name', '=', line['State Name'])]).id,
                                        'zip': line['PIN CODE'],
                                        'ar_zip': line['PIN CODE ARABIC'],
                                        'country_id': self.env['res.country'].sudo().search(
                                            [('name', '=', line['Country'])]).id,
                                        'ar_country': line['CountryArabic'],
                                        'vat': line['VAT No'],
                                        'ar_tax_id': line['VAT No Arabic'],
                                        'type_of_customer': line['Type of customer'],
                                        'schema_id': line['schemeID'],
                                        'schema_id_no': line['scheme Number'],
                                        'building_no': line['Building Number'],
                                        'plot_id': line['Plot Identification'],
                                    })

                                    partner_id = partner_details
                                else:
                                    partner_id = self.env['res.partner'].sudo().create({
                                        'name': line['Customer Name'],
                                        'ar_name': line['Customer Name Arabic'],
                                        'phone': line['Mobile Number'],
                                        'cust_code': line['CUST_CODE'],
                                        'ar_phone': line['Mobile Number Arabic'],
                                        'street': line['Street Name'],
                                        'street2': line['Street2 Name'],
                                        'city': line['City'],
                                        'state_id': self.env['res.country.state'].sudo().search(
                                            [('name', '=', line['State Name'])]).id,
                                        'zip': line['PIN CODE'],
                                        'ar_zip': line['PIN CODE ARABIC'],
                                        'country_id': self.env['res.country'].sudo().search(
                                            [('name', '=', line['Country'])]).id,
                                        'ar_country': line['CountryArabic'],
                                        'vat': line['VAT No'],
                                        'ar_tax_id': line['VAT No Arabic'],
                                        'type_of_customer': line['Type of customer'],
                                        'schema_id': line['schemeID'],
                                        'schema_id_no': line['scheme Number'],
                                        'building_no': line['Building Number'],
                                        'plot_id': line['Plot Identification'],
                                    })
                                invoice_list = []
                                for inv_line in line['Invoice lines']:
                                    product = self.env['product.product'].sudo().search(
                                        [('name', '=', inv_line['Product Name'])])
                                    if not product:
                                        product = self.env['product.template'].sudo().create({
                                            'name': inv_line['Product Name'],
                                            'type': 'service',
                                            'invoice_policy': 'order',
                                        })
                                    invoice_list.append((0, 0, {
                                        'name': inv_line['description'],
                                        'price_unit': inv_line['Price'],
                                        'quantity': inv_line['Quantity'],
                                        'discount': inv_line['Discount'],
                                        'product_uom_id': self.env['uom.uom'].sudo().search(
                                            [('name', '=', inv_line['UoM'])]).id,
                                        'vat_category': inv_line['Vat Category'],
                                        'product_id': product.id,
                                        'tax_ids': [(6, 0, self.env['account.tax'].sudo().search(
                                            [('name', '=', inv_line['Taxes']), ('type_tax_use', '=', 'sale')]).ids)]}))
                                invoice_date = (line['InvoiceDate'].split(" ")[0]).split("/")
                                month = invoice_date[0]
                                day = invoice_date[1]
                                year = invoice_date[2]

                                # ar_amount_total = fields.Char('Total')
                                # ar_amount_untaxed = fields.Char('Untaxed Amount')
                                # ar_amount_tax = fields.Char('Taxes')
                                # amount_in_word_en = fields.Char()
                                # amount_in_word_ar = fields.Char()
                                # amount_in_word_vat_en = fields.Char()
                                # amount_in_word_vat_ar = fields.Char()
                                # arabic_date = fields.Char()

                                account_move = self.env['account.move'].sudo().create({
                                    'partner_id': partner_id[0].id,
                                    'invoice_line_ids': invoice_list,
                                    'move_type': line['Invoice Type'],
                                    'payment_mode': line['Payment Mode'],
                                    'contact': line['Address Contact'],
                                    'contact_address': line['Address Contact Arabic'],
                                    'payment_reference': line['payment reference'],
                                    # 'invoice_date': year+'-'+month+'-'+day ,
                                    'system_inv_no': line['InvoiceNo'],
                                    'a_total_amount': line['A_TOTAL_VALUE'],
                                    'a_net_amount': line['A_NET_AMOUNT'],
                                    'a_vat_value': line['A_VAT_VALUE'],
                                    'a_net_with_value': line['A_NET_WITH_VAT'],
                                    'invoice_nat_time': line['INVOICE_DATETIME'],
                                    'customer_po': line['PONO'],
                                    'compute_test_send_test': True,
                                    'ar_amount_untaxed': line['Word without vat'],
                                    'amount_in_word_ar': line['Word with vat'],
                                    'system_inv_no_ar': line['InvoiceNoArabic'],
                                    'invoice_date_time': line['InvoiceDate'],
                                    'advance_with_vat': line['ADVANCE_WITH_VAT'],
                                    'a_advance_with_vat': line['A_ADVANCE_WITH_VAT'],
                                    'invoice_date_time_ar': line['InvoiceDateArabic'],
                                    'sales_man': line['Salesman Name'],
                                    'so_number': line['SO No'],
                                    'curr_code': line['CURR_CODE'],
                                    'remarks': line['ANNOTATION'],
                                    'advance': line['ADVANCE'],
                                    'ar_advance': line['ADVANCE_A'],
                                    'exchg_rate': line['EXCHG_RATE'],
                                    'discount_value': line['DISCOUNT_VALUE'],
                                    'discount_value_a': line['DISCOUNT_VALUE_A'],
                                    'word_without_vat_english': line['Word without vat english'],
                                    'word_with_vat_english': line['Word with vat english'],
                                    'address_contact': line['Address Contact'],
                                    'address_contact_ar': line['Address Contact Arabic'],
                                })
                                invoice_no = line['InvoiceNo']
                                invoice_date = line['InvoiceDate']
                                if self.env['einvoice.admin'].search([]):

                                    account_move.admin_mail = self.env['einvoice.admin'].search([])[-1].name.id
                                    #         template_id = self.env['mail.template'].sudo().search([('name', '=', 'Invoice: Send by email B2B')]).id
                                    #         template = self.env['mail.template'].browse(template_id)
                                    #         template.send_mail(self.id, force_send=True)


                                    # self.admin_mail = self.env['einvoice.admin'].search([])[-1].name.id
                                    template_id = self.env['mail.template'].sudo().search(
                                        [('name', '=', 'Invoice: Send by email Information')]).id
                                    if template_id:
                                        print('yes......',account_move)
                                        template = self.env['mail.template'].browse(template_id)
                                        template.send_mail(account_move.id, force_send=True)

                                # account_move.sudo().action_post()
                                # if account_move:
                                #     import datetime
                                #     # date = datetime.date(account_move.invoice_date.year, account_move.invoice_date.month,
                                #     #                      account_move.invoice_date.day)
                                #     # month = invoice_date[0]
                                #     # day = invoice_date[1]
                                #     # year = invoice_date[2]
                                #     tota = line['INVOICE_DATETIME'].rsplit(' ')[1].rsplit(':')
                                #     hr = int(tota[0])
                                #     min = int(tota[1])
                                #     sec = int(tota[2])
                                #     import datetime
                                #     times = datetime.time(hr,min,sec)
                                #     # datetime.time(each.datetime_field.time().hour, each.datetime_field.time().minute)
                                #     account_move.invoice_nat_times = datetime.datetime.combine(account_move.invoice_date,times)

                            if line_data:
                                json_data.system_inv_no = invoice_no
                                json_data.invoice_date_time = invoice_date


    def callrequest1(self):
        if self.env['json.configuration'].search([]):
            link = self.env['json.configuration'].search([])[-1].name
            link_no = self.env['json.configuration'].search([])[-1].no_of_invoices
            responce = requests.get(link)
            if responce:
                line_data = json.loads(responce.text)
                invoice_no = None
                invoice_date = None
                invoice_length = 0
                line_data.reverse()
                for line in line_data:
                    if invoice_length <= link_no:
                        old_invoice = self.env['account.move'].search([('system_inv_no', '=', line['InvoiceNo'])])
                        if not old_invoice:
                            invoice_length += 1
                            partner_details = self.env['res.partner'].sudo().search(
                                [('name', '=', line['Customer Name'])])
                            if partner_details:
                                partner_id = self.env['res.partner'].sudo().update({
                                    'name': line['Customer Name'],
                                    'ar_name': line['Customer Name Arabic'],
                                    'phone': line['Mobile Number'],
                                    'cust_code': line['CUST_CODE'],
                                    'ar_phone': line['Mobile Number Arabic'],
                                    'street': line['Street Name'],
                                    'street2': line['Street2 Name'],
                                    'city': line['City'],
                                    'state_id': self.env['res.country.state'].sudo().search(
                                        [('name', '=', line['State Name'])]).id,
                                    'zip': line['PIN CODE'],
                                    'ar_zip': line['PIN CODE ARABIC'],
                                    'country_id': self.env['res.country'].sudo().search(
                                        [('name', '=', line['Country'])]).id,
                                    'ar_country': line['CountryArabic'],
                                    'vat': line['VAT No'],
                                    'ar_tax_id': line['VAT No Arabic'],
                                    'type_of_customer': line['Type of customer'],
                                    'schema_id': line['schemeID'],
                                    'schema_id_no': line['scheme Number'],
                                    'building_no': line['Building Number'],
                                    'plot_id': line['Plot Identification'],
                                })
                                partner_id = partner_details

                            else:
                                partner_id = self.env['res.partner'].sudo().create({
                                    'name': line['Customer Name'],
                                    'ar_name': line['Customer Name Arabic'],
                                    'phone': line['Mobile Number'],
                                    'cust_code': line['CUST_CODE'],
                                    'ar_phone': line['Mobile Number Arabic'],
                                    'street': line['Street Name'],
                                    'street2': line['Street2 Name'],
                                    'city': line['City'],
                                    'compute_test_send_test': True,
                                    'state_id': self.env['res.country.state'].sudo().search(
                                        [('name', '=', line['State Name'])]).id,
                                    'zip': line['PIN CODE'],
                                    'ar_zip': line['PIN CODE ARABIC'],
                                    'country_id': self.env['res.country'].sudo().search(
                                        [('name', '=', line['Country'])]).id,
                                    'ar_country': line['CountryArabic'],
                                    'vat': line['VAT No'],
                                    'ar_tax_id': line['VAT No Arabic'],
                                    'type_of_customer': line['Type of customer'],
                                    'schema_id': line['schemeID'],
                                    'schema_id_no': line['scheme Number'],
                                    'building_no': line['Building Number'],
                                    'plot_id': line['Plot Identification'],
                                })
                            invoice_list = []
                            for inv_line in line['Invoice lines']:
                                product = self.env['product.product'].sudo().search(
                                    [('name', '=', inv_line['Product Name'])])
                                if not product:
                                    product = self.env['product.template'].sudo().create({
                                        'name': inv_line['Product Name'],
                                        'type': 'service',
                                        'invoice_policy': 'order',
                                    })
                                invoice_list.append((0, 0, {
                                    'name': inv_line['description'],
                                    'price_unit': inv_line['Price'],
                                    'quantity': inv_line['Quantity'],
                                    'discount': inv_line['Discount'],
                                    'product_uom_id': self.env['uom.uom'].sudo().search(
                                        [('name', '=', inv_line['UoM'])]).id,
                                    'vat_category': inv_line['Vat Category'],
                                    'product_id': product.id,
                                    'tax_ids': [(6, 0, self.env['account.tax'].sudo().search(
                                        [('name', '=', inv_line['Taxes']), ('type_tax_use', '=', 'sale')]).ids)]}))
                            invoice_date = (line['InvoiceDate'].split(" ")[0]).split("/")
                            month = invoice_date[0]
                            day = invoice_date[1]
                            year = invoice_date[2]
                            # tota = line['INVOICE_DATETIME'].rsplit(' ')[1].rsplit(':')
                            # import datetime
                            # hr = int(tota[0])
                            # min = int(tota[1])
                            # sec = int(tota[2])
                            # time = datetime.time(hr,hr)
                            # # datetime.time(each.datetime_field.time().hour, each.datetime_field.time().minute)
                            # # account_move.invoice_nat_times = datetime.datetime.combine(date, time)

                            account_move = self.env['account.move'].sudo().create({
                                'partner_id': partner_id.id,
                                'invoice_line_ids': invoice_list,
                                'move_type': line['Invoice Type'],
                                'payment_mode': line['Payment Mode'],
                                'payment_reference': line['payment reference'],
                                # 'invoice_date': year+'-'+month+'-'+day ,
                                'system_inv_no': line['InvoiceNo'],
                                'customer_po': line['PONO'],
                                'invoice_nat_time': line['INVOICE_DATETIME'],
                                'ar_amount_untaxed': line['Word without vat'],
                                'advance_with_vat': line['ADVANCE_WITH_VAT'],
                                'a_total_amount': line['A_TOTAL_VALUE'],
                                'a_net_amount': line['A_NET_AMOUNT'],
                                'a_vat_value': line['A_VAT_VALUE'],
                                'a_net_with_value': line['A_NET_WITH_VAT'],
                                'a_advance_with_vat': line['A_ADVANCE_WITH_VAT'],
                                'amount_in_word_ar': line['Word with vat'],
                                'system_inv_no_ar': line['InvoiceNoArabic'],
                                'invoice_date_time': line['InvoiceDate'],
                                'invoice_date_time_ar': line['InvoiceDateArabic'],
                                'contact': line['Address Contact'],
                                'contact_address': line['Address Contact Arabic'],
                                'sales_man': line['Salesman Name'],
                                'so_number': line['SO No'],
                                'remarks': line['ANNOTATION'],
                                'curr_code': line['CURR_CODE'],
                                'advance': line['ADVANCE'],
                                'ar_advance': line['ADVANCE_A'],
                                'exchg_rate': line['EXCHG_RATE'],
                                'discount_value': line['DISCOUNT_VALUE'],
                                'discount_value_a': line['DISCOUNT_VALUE_A'],
                                'word_without_vat_english': line['Word without vat english'],
                                'word_with_vat_english': line['Word with vat english'],
                                'address_contact': line['Address Contact'],
                                'address_contact_ar': line['Address Contact Arabic'],
                            })
                            print(account_move)
                            invoice_no = line['InvoiceNo']
                            invoice_date = line['InvoiceDate']
                            account_move.action_post()
                            if account_move:
                                import datetime
                                # date = datetime.date(account_move.invoice_date.year, account_move.invoice_date.month,
                                #                      account_move.invoice_date.day)
                                # month = invoice_date[0]
                                # day = invoice_date[1]
                                # year = invoice_date[2]
                                tota = line['INVOICE_DATETIME'].rsplit(' ')[1].rsplit(':')
                                hr = int(tota[0])
                                min = int(tota[1])
                                sec = int(tota[2])
                                import datetime
                                times = datetime.time(hr, min, sec)
                                # datetime.time(each.datetime_field.time().hour, each.datetime_field.time().minute)
                                account_move.invoice_nat_times = datetime.datetime.combine(account_move.invoice_date,
                                                                                           times)

                        if line_data:
                            self.system_inv_no = invoice_no
                            self.invoice_date_time = invoice_date

class MailMail(models.Model):
    """ Model holding RFC2822 email messages to send. This model also provides
        facilities to queue and send new email messages.  """
    _inherit = 'mail.mail'

    # def _send(self, auto_commit=False, raise_exception=False, smtp_session=None):
    #     IrMailServer = self.env['ir.mail_server']
    #     IrAttachment = self.env['ir.attachment']
    #     for mail_id in self.ids:
    #             success_pids = []
    #             failure_type = None
    #             processing_pid = None
    #             mail = None
    #         # try:
    #             mail = self.browse(mail_id)
    #             if mail.state != 'outgoing':
    #                 if mail.state != 'exception' and mail.auto_delete:
    #                     mail.sudo().unlink()
    #                 continue
    #
    #             # remove attachments if user send the link with the access_token
    #             body = mail.body_html or ''
    #             attachments = mail.attachment_ids
    #             for link in re.findall(r'/web/(?:content|image)/([0-9]+)', body):
    #                 attachments = attachments - IrAttachment.browse(int(link))
    #
    #             # load attachment binary data with a separate read(), as prefetching all
    #             # `datas` (binary field) could bloat the browse cache, triggerring
    #             # soft/hard mem limits with temporary data.
    #             attachments = [(a['name'], base64.b64decode(a['datas']), a['mimetype'])
    #                            for a in attachments.sudo().read(['name', 'datas', 'mimetype']) if a['datas'] is not False]
    #
    #             for a in attachments.read(['name', 'datas', 'mimetype']):
    #                 print(attachments.read(['name', 'datas', 'mimetype']))
    #
    #             # specific behavior to customize the send email for notified partners
    #             email_list = []
    #             if mail.email_to:
    #                 email_list.append(mail._send_prepare_values())
    #             for partner in mail.recipient_ids:
    #                 values = mail._send_prepare_values(partner=partner)
    #                 values['partner_id'] = partner
    #                 email_list.append(values)
    #
    #             # headers
    #             headers = {}
    #             ICP = self.env['ir.config_parameter'].sudo()
    #             bounce_alias = ICP.get_param("mail.bounce.alias")
    #             bounce_alias_static = tools.str2bool(ICP.get_param("mail.bounce.alias.static", "False"))
    #             catchall_domain = ICP.get_param("mail.catchall.domain")
    #             if bounce_alias and catchall_domain:
    #                 if bounce_alias_static:
    #                     headers['Return-Path'] = '%s@%s' % (bounce_alias, catchall_domain)
    #                 elif mail.mail_message_id.is_thread_message():
    #                     headers['Return-Path'] = '%s+%d-%s-%d@%s' % (bounce_alias, mail.id, mail.model, mail.res_id, catchall_domain)
    #                 else:
    #                     headers['Return-Path'] = '%s+%d@%s' % (bounce_alias, mail.id, catchall_domain)
    #             # if mail.headers:
    #             #     try:
    #             #         headers.update(ast.literal_eval(mail.headers))
    #             #     except Exception:
    #             #         pass
    #
    #             # Writing on the mail object may fail (e.g. lock on user) which
    #             # would trigger a rollback *after* actually sending the email.
    #             # To avoid sending twice the same email, provoke the failure earlier
    #             mail.write({
    #                 'state': 'exception',
    #                 'failure_reason': _('Error without exception. Probably due do sending an email without computed recipients.'),
    #             })
    #             # Update notification in a transient exception state to avoid concurrent
    #             # update in case an email bounces while sending all emails related to current
    #             # mail record.
    #             notifs = self.env['mail.notification'].search([
    #                 ('notification_type', '=', 'email'),
    #                 ('mail_id', 'in', mail.ids),
    #                 ('notification_status', 'not in', ('sent', 'canceled'))
    #             ])
    #             if notifs:
    #                 notif_msg = _('Error without exception. Probably due do concurrent access update of notification records. Please see with an administrator.')
    #                 notifs.sudo().write({
    #                     'notification_status': 'exception',
    #                     'failure_type': 'UNKNOWN',
    #                     'failure_reason': notif_msg,
    #                 })
    #                 # `test_mail_bounce_during_send`, force immediate update to obtain the lock.
    #                 # see rev. 56596e5240ef920df14d99087451ce6f06ac6d36
    #                 notifs.flush(fnames=['notification_status', 'failure_type', 'failure_reason'], records=notifs)
    #
    #             # build an RFC2822 email.message.Message object and send it without queuing
    #             res = None
    #             for email in email_list:
    #                 msg = IrMailServer.build_email(
    #                     email_from=mail.email_from,
    #                     email_to=email.get('email_to'),
    #                     subject=mail.subject,
    #                     body=email.get('body'),
    #                     body_alternative=email.get('body_alternative'),
    #                     email_cc=tools.email_split(mail.email_cc),
    #                     reply_to=mail.reply_to,
    #                     attachments=attachments,
    #                     message_id=mail.message_id,
    #                     references=mail.references,
    #                     object_id=mail.res_id and ('%s-%s' % (mail.res_id, mail.model)),
    #                     subtype='html',
    #                     subtype_alternative='plain',
    #                     headers=headers)
    #                 processing_pid = email.pop("partner_id", None)
    #                 try:
    #                     res = IrMailServer.send_email(
    #                         msg, mail_server_id=mail.mail_server_id.id, smtp_session=smtp_session)
    #                     if processing_pid:
    #                         success_pids.append(processing_pid)
    #                     processing_pid = None
    #                 except AssertionError as error:
    #                     if str(error) == IrMailServer.NO_VALID_RECIPIENT:
    #                         failure_type = "RECIPIENT"
    #                         # No valid recipient found for this particular
    #                         # mail item -> ignore error to avoid blocking
    #                         # delivery to next recipients, if any. If this is
    #                         # the only recipient, the mail will show as failed.
    #                         _logger.info("Ignoring invalid recipients for mail.mail %s: %s",
    #                                      mail.message_id, email.get('email_to'))
    #                     else:
    #                         raise
    #             if res:  # mail has been sent at least once, no major exception occured
    #                 mail.write({'state': 'sent', 'message_id': res, 'failure_reason': False})
    #                 _logger.info('Mail with ID %r and Message-Id %r successfully sent', mail.id, mail.message_id)
    #                 # /!\ can't use mail.state here, as mail.refresh() will cause an error
    #                 # see revid:odo@openerp.com-20120622152536-42b2s28lvdv3odyr in 6.1
    #             mail._postprocess_sent_message(success_pids=success_pids, failure_type=failure_type)
    #         # except MemoryError:
    #         #     # prevent catching transient MemoryErrors, bubble up to notify user or abort cron job
    #         #     # instead of marking the mail as failed
    #         #     _logger.exception(
    #         #         'MemoryError while processing mail with ID %r and Msg-Id %r. Consider raising the --limit-memory-hard startup option',
    #         #         mail.id, mail.message_id)
    #         #     # mail status will stay on ongoing since transaction will be rollback
    #         #     raise
    #         # except (psycopg2.Error, smtplib.SMTPServerDisconnected):
    #         #     # If an error with the database or SMTP session occurs, chances are that the cursor
    #         #     # or SMTP session are unusable, causing further errors when trying to save the state.
    #         #     _logger.exception(
    #         #         'Exception while processing mail with ID %r and Msg-Id %r.',
    #         #         mail.id, mail.message_id)
    #         #     raise
    #         # except Exception as e:
    #         #     failure_reason = tools.ustr(e)
    #         #     _logger.exception('failed sending mail (id: %s) due to %s', mail.id, failure_reason)
    #         #     mail.write({'state': 'exception', 'failure_reason': failure_reason})
    #         #     mail._postprocess_sent_message(success_pids=success_pids, failure_reason=failure_reason, failure_type='UNKNOWN')
    #         #     if raise_exception:
    #         #         if isinstance(e, (AssertionError, UnicodeEncodeError)):
    #         #             if isinstance(e, UnicodeEncodeError):
    #         #                 value = "Invalid text: %s" % e.object
    #         #             else:
    #         #                 value = '. '.join(e.args)
    #         #             raise MailDeliveryException(value)
    #         #         raise
    #
    #             if auto_commit is True:
    #                 self._cr.commit()
    #     return True
