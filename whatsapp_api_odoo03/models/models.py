# -*- coding: utf-8 -*-

from odoo import models, fields, api
import base64
import requests
from odoo.exceptions import UserError, ValidationError, AccessError, RedirectWarning
import json    
from odoo import http,SUPERUSER_ID
import os
from datetime import datetime, timedelta
import re
import mimetypes
from datetime import date
import tempfile
from odoo.tools import config
from odoo import models, fields, api
from markupsafe import Markup



def check_subscription_expiration(env):
    """
    Returns:
        True  -> Subscription active
        False -> Subscription expired or not found
    """

    last_plan = env['whatsapp.payment.wizard'].search(
        [],
        order='end_datetime desc',
        limit=1
    )

    if not last_plan or not last_plan.end_datetime:
        return False

    now = fields.Datetime.now()

    return last_plan.end_datetime >= now


class WhatsaapCustomer(models.Model):
    _inherit ="res.partner"

    whatsapp_customer_id = fields.Char(string="whatsapp_customer_id")
    chat_active_timer = fields.Char(string="chat activate timer")
    chatactive = fields.Boolean(default=False)
    chat_activated_at = fields.Datetime(string="Chat Activated At")
    ticketId =fields.Char(string="ticketId")
    customerId =fields.Char(string="customerId")
    userId =fields.Char(string="userId")
    mobile=fields.Char(string="Mobile")

    def product_create_daily(self):
 
        try:
            host = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

            url = "http://localhost:8000/CreateSalesOrder"
            finalResponse = requests.get(url) 

        except:
            pass  

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        # Call the original validation first
        res = super().button_validate()
        # Send WhatsApp message only for done pickings
        for picking in self:

            if self.state == "draft":
                triger_state= "delivery_in_draft"
            elif self.state == "assigned":  
                triger_state= "delivery_in_assigned"  
            elif self.state == "done":   
                triger_state= "delivery_in_done"
            else:
                triger_state= None

            if triger_state != None:
                # Filter whatsapp.trigger for current model & send_type = pdf
                triggers = self.env['whatsapp.trigger'].search([
                    ('model_id.model', '=', self._name),
                    ('send_type', 'in', ['text', 'pdf','pdf-text']),
                    ('trigger_state', '=',triger_state ),
                    ('trigger_automatically', '=', True)
                ])
                if triggers:
                    self.action_send_whatsapp()
            else:
                pass        
                   
        return res
    
    def send_notification_on_whatsapp(self,whatsorderid):
        try:
            import requests
            import json

            setting_object = self.env["ir.config_parameter"].sudo()
            apikey = setting_object.get_param("apikey")
            secureKey = setting_object.get_param("secureKey")

            url = f"/developerApi/updateCatalogOrderDeliveryStatus/v1/{apikey}/{secureKey}"
            url = setting_object.get_param("go4whatsapp_url") + url

            payload = json.dumps({
            "catalogOrderId": whatsorderid,
            "deliveryStatus": "done"
            })
            headers = {
            'Content-Type': 'application/json',
            'Cookie': 'HttpOnly; HttpOnly'
            }
            response = requests.request("POST", url, headers=headers, data=payload)

            print(response.text)

        except Exception as e:
            pass        

    def send_delivery_pdf_for_whatsapp(self):
        if self.env.user.go4whatsapp_access_token:
            try:
                endpoint = "/sendDocumentINOddo"
                if not self.partner_id.country_id:
                    raise UserError("Please select a country for the customer.")
                if not self.partner_id.mobile:
                    raise UserError("Invalid mobile number.")

                # Format mobile number
                mobile_no = f"{self.partner_id.mobile}"

                # Get config values
                setting_object = self.env["ir.config_parameter"].sudo()
                url = setting_object.get_param("go4whatsapp_url") + endpoint
                template_id = setting_object.get_param("template_id")
                org_id = setting_object.get_param("org_id")

                apikey = setting_object.get_param("apikey")
                secureKey = setting_object.get_param("secureKey")
                shippingTemplatedId = setting_object.get_param("shippingTemplatedId")

                url = f"/developerApi/sendTemplateWithVariable/v1/{apikey}/{secureKey}"
                url = setting_object.get_param("go4whatsapp_url") + url

                payload= {
                    "templateId":shippingTemplatedId,
                    "mobileNo":  mobile_no,
                    "variablesHeader":[
                    # {
                    # "variableKey":"",
                    # "variableValue":""
                    # }
                    ],
                    "variablesBody":[
                    # {
                    # "variableKey":"",
                    # "variableValue":""
                    # }
                    ]
                    }
                
                headers = {}
                # Send the request
                # response = requests.post(url, headers=headers, data=payload, files=files)
                response = requests.post(url, headers=headers, data=payload)
                print("Response Status Code:", response.status_code)
                if response.status_code == 200:
                    print(" Delivery Order PDF sent via WhatsApp.", response.json())
                else:
                    print(" Failed to send PDF:", response.status_code, response.text)

            except Exception as e:
                print(" Error while sending WhatsApp PDF:", str(e))

    def action_send_whatsapp(self):

        if self.state == "draft":
            triger_state= "delivery_in_draft"
        elif self.state == "assigned":  
            triger_state= "delivery_in_assigned"  
        elif self.state == "done":   
            triger_state= "delivery_in_done"
        else:
            triger_state= "delivery_in_done"

        all_results = []
        order_values = {}
        
        if triger_state != None:
            # Filter whatsapp.trigger for current model & send_type = pdf
            triggers = self.env['whatsapp.trigger'].search([
                ('model_id.model', '=', self._name),
                ('send_type', 'in', ['text', 'pdf','pdf-text']),
                ('trigger_state', '=',triger_state )
            ])

            for trigger in triggers:
                trigger_data = trigger.read()[0]  # get all fields as dict
                trg_id=trigger_data["id"]
                fetch_fields = self.env['whatsapp.trigger.field.mapping'].search([
                ('trigger_id', '=', trg_id)
                ])

                if fetch_fields:
                    fetch_fields_data = fetch_fields.read(['model_field_id', 'template_field'])

                    for field_mapping in fetch_fields_data:
                        template_field = field_mapping.get('template_field')
                        model_field = field_mapping.get('model_field_id')

                        # Special case: username → partner name
                        if template_field == 'username' or template_field == 'name' :
                            order_values[template_field] = self.partner_id.name if self.partner_id else None
                            continue

                        # Normal case: get value from model_field_id
                        if model_field:
                            field_id = model_field[0]  # Many2one tuple
                            field_rec = self.env['ir.model.fields'].browse(field_id)
                            if field_rec and field_rec.name:
                                value = getattr(self, field_rec.name, False)
                                order_values[template_field] = value
                            else:
                                order_values[template_field] = None
                        else:
                            order_values[template_field] = None       
                else:
                    pass   

                try:

                    if trigger_data["send_type"] != "text":
                        data = self.env['ir.actions.report'].sudo()._render_qweb_pdf('stock.action_report_delivery', [self.id])[0]
                        safe_filename = self.name.replace("/", "_") + ".pdf"
                        temp_dir = tempfile.gettempdir()
                        file_path = os.path.join(temp_dir, safe_filename)
                        with open(file_path, 'wb') as file:
                            file.write(data)
                        mime_type, _ = mimetypes.guess_type(file_path)
                        if mime_type != "application/pdf":
                            raise UserError("Generated file is not a valid PDF.")
                        files=[('file',(f'{self.name}.pdf',open(file_path,'rb'),'application/pdf'))]

                        # PDF Chatter me attachment ke sath show
                        self.message_post(
                            body=f"A PDF {self.name}.pdf has been generated and sent to the customer.",
                            attachments=[(
                               f"{self.name}.pdf",
                                data
                            )]
                        )  

                    else:
                       files=[] 

                except Exception as e:
                    pass    
                
                setting_object = self.env["ir.config_parameter"].sudo()
                url = setting_object.get_param("go4whatsapp_url")
                org_id = setting_object.get_param("org_id")
                mobile_no = f"{self.partner_id.mobile}"
                
                    # ✅ safely handle all cases   
                if order_values and isinstance(order_values, dict) and len(order_values) > 0:
                    variables_list = [
                        {"variableKey": k, "variableValue": (
                            v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v
                        )}
                        for k, v in order_values.items()
                    ]
                    variables_body = json.dumps(variables_list)
                else:
                    variables_list = []  # empty list if no data

                variables_body = json.dumps(variables_list)    
                try:
                    import requests
                    url = f"{url}/sendAttachmentWithVariableForOdoo"
                    payload = {'orgId': org_id,
                    'templateId': trigger.Whatsapp_template.template_id,
                    'mobileNo': mobile_no,
                    'variablesBody': f'{variables_body}'}




                    files=files
                    headers = {}
                    response = requests.request("POST", url, headers=headers, data=payload, files=files)
                    print(response)
                except Exception as e:
                    pass    

        return all_results

class WhatsappProductOrder(models.Model):
    _inherit ="product.product"

    whatsapp_product_id = fields.Char(string="whatsapp_product_id")

class SaleOrder(models.Model):
    _inherit ="sale.order"

    whatsapp_sale_order_id = fields.Char(string="whatsapp_sale_order_id")
    language_name = fields.Selection(
    selection=[
            ('en', 'English'),
            ('ar', 'Arabic')
        ],
        string='Language',
        help="Product language",
        default='en'
    )
    custom_check_field = fields.Boolean(string="Go4Whatsapp order", compute="_compute_custom_check")

    @api.model
    def create(self, vals):
        record = super(SaleOrder, self).create(vals)
        print(".....sales order created.....", record.state)

        # Determine trigger state based on the new record
        if not record.state or record.state == "draft":
            triger_state = "sale_draft"
        else:
            triger_state = None

        if triger_state:
            # Filter whatsapp.trigger for current model & send_type = pdf
            triggers = self.env['whatsapp.trigger'].search([
                ('model_id.model', '=', self._name),
                ('send_type', 'in', ['text', 'pdf', 'pdf-text']),
                ('trigger_state', '=', triger_state),
                ('trigger_automatically', '=', True)
            ])
            if triggers:
                # Call method on the newly created record
                record.send_pdf_for_whatsapp_on_web_side_sale()
        return record

    def write(self, vals):
        res = super(SaleOrder, self).write(vals)
        if 'state' in vals:
            print("send_pdf_for_whatsapp_on_web_side_sale...", self._name,self.state)
            if self.state == "draft":
                triger_state= "sale_draft"
            elif self.state == "sent":  
                triger_state= "sale_sent"  
            elif self.state == "sale":   
                triger_state= "sale_confirmed"  
            elif self.state == "cancel":   
                triger_state= "sale_cancel"    
            else:
                triger_state= None

            if triger_state != None:
                # Filter whatsapp.trigger for current model & send_type = pdf
                triggers = self.env['whatsapp.trigger'].search([
                    ('model_id.model', '=', self._name),
                    ('send_type', 'in', ['text', 'pdf','pdf-text']),
                    ('trigger_state', '=',triger_state),
                    ('trigger_automatically', '=', True)
                ])
                if triggers:
                   print("hitting from automatically side..")
                   self.send_pdf_for_whatsapp_on_web_side_sale()
        return res

    def _compute_custom_check(self):
        for rec in self:
            rec.custom_check_field = bool(rec.whatsapp_sale_order_id)
    
    def action_confirm(self):

        res = super(SaleOrder, self).action_confirm()
        self.send_pdf_for_whatsapp()
        return res
    
    def send_pdf_for_whatsapp(self):

        print("template send.........", self._name,self.state)

        if self.whatsapp_sale_order_id:
            try:
                endpoint = "/sendDocumentINOddo"
                # Ensure the data is properly decoded as binary data
                data = self.env['ir.actions.report'].sudo()._render_qweb_pdf('sale.action_report_saleorder', [self.id])[0]
                safe_filename = self.name.replace("/", "_") + ".pdf"
                temp_dir = tempfile.gettempdir()
                print("code working....")
                file_path = os.path.join(temp_dir, safe_filename)

                # Write binary data to the file
                with open(file_path, 'wb') as file:
                    file.write(data)

                mime_type, _ = mimetypes.guess_type(file_path)
                if mime_type != "application/pdf":
                    raise UserError("Generated file is not a valid PDF.")

                # Validate partner details
                if not self.partner_id.country_id:
                    raise UserError('Please select country from customer')
                if not self.partner_id.mobile:
                    raise UserError('Invalid Number')

                mobile_no = f"{self.partner_id.mobile}"

                setting_object = self.env["ir.config_parameter"].sudo()
                url = setting_object.get_param("go4whatsapp_url") + endpoint
                template_id = setting_object.get_param("template_id")
                org_id = setting_object.get_param("org_id")

                files=[
                ('file',(f'{self.name}.pdf',open(file_path,'rb'),'application/pdf'))
                ]

                message = f'''
                    Hello {self.partner_id.name},\n We have successfully received your payment of {self.amount_total} \nYour order has been confirmed. Please find the sales order attached with this message.
                '''

                payload = {
                    "moNumber": mobile_no,
                    "templatedId": template_id,
                    "orgId": org_id,
                    "userName": self.partner_id.name,
                    "documentType": "text-pdf",
                    "filename":"sales order.pdf",
                    "message":message
                }
                
                headers = {
                    # 'Authorization': f'Bearer {self.env.user.go4whatsapp_access_token}',
                    # 'Content-Type': 'application/pdf'
                }

                # response = requests.request("POST", url, headers=headers, data=payload, files=files)

                # if response.status_code == 200:
                #     print("File sent successfully.", response.json())
                # else:
                #     print("Failed to send file:", response.status_code, response.text)

            except Exception as e:
                pass

        else:
            pass
    
    def send_pdf_for_whatsapp_on_web_side_sale(self):
        check_subscription= self.env['whatsapp.payment.wizard'].check_subscription_expiration()
        if check_subscription == False:
             raise UserError("Your WhatsApp Connector monthly plan has expired.")

        print("send_pdf_for_whatsapp_on_web_side_sale...", self._name,self.state,"....",self)
        if self.state == "draft" or self.state == False:
            triger_state= "sale_draft"
        elif self.state == "sent":  
            triger_state= "sale_sent"  
        elif self.state == "sale":   
            triger_state= "sale_confirmed"  
        elif self.state == "cancel":   
            triger_state= "sale_cancel"    
        else:
            triger_state= None

        all_results = []
        order_values = {}
        
        if triger_state != None:
            # Filter whatsapp.trigger for current model & send_type = pdf
            triggers = self.env['whatsapp.trigger'].search([
                ('model_id.model', '=', self._name),
                ('send_type', 'in', ['text', 'pdf','pdf-text']),
                ('trigger_state', '=',triger_state )
            ])

            for trigger in triggers:
                trigger_data = trigger.read()[0]  # get all fields as dict
                trg_id=trigger_data["id"]
                fetch_fields = self.env['whatsapp.trigger.field.mapping'].search([
                ('trigger_id', '=', trg_id)
                ])

                if fetch_fields:
                    fetch_fields_data = fetch_fields.read(['model_field_id', 'template_field'])

                    for field_mapping in fetch_fields_data:
                        template_field = field_mapping.get('template_field')
                        model_field = field_mapping.get('model_field_id')

                        # Special case: username → partner name
                        if template_field == 'username' or template_field == 'name' :
                            order_values[template_field] = self.partner_id.name if self.partner_id else None
                            continue

                        # Normal case: get value from model_field_id.
                        if model_field:
                            field_id = model_field[0]  # Many2one tuple.
                            field_rec = self.env['ir.model.fields'].browse(field_id)
                            if field_rec and field_rec.name:
                                value = getattr(self, field_rec.name, False)
                                order_values[template_field] = value
                            else:
                                order_values[template_field] = None
                        else:
                            order_values[template_field] = None       
                else:
                    pass   

                try:

                    if trigger_data["send_type"] != "text":
                        data = self.env['ir.actions.report'].sudo()._render_qweb_pdf('sale.action_report_saleorder', [self.id])[0]
                        safe_filename = self.name.replace("/", "_") + ".pdf"
                        temp_dir = tempfile.gettempdir()
                        file_path = os.path.join(temp_dir, safe_filename)
                        with open(file_path, 'wb') as file:
                            file.write(data)
                        mime_type, _ = mimetypes.guess_type(file_path)
                        if mime_type != "application/pdf":
                            raise UserError("Generated file is not a valid PDF.")
                        files=[('file',(f'{self.name}.pdf',open(file_path,'rb'),'application/pdf'))]

                        # PDF Chatter me attachment ke sath show
                        self.message_post(
                            body=f"Sales order PDF {self.name}.pdf has been generated and sent to the customer.",
                            attachments=[(
                                f"{self.name}.pdf",
                                data
                            )]
                        )   

                        

                    else:
                       files=[] 


                    create_msg=self.env["whatsapp.chat.message"].sudo()
                    vals = {
                    "partner_id": self.partner_id.id,
                    "message": trigger.Whatsapp_template.body_text,
                    "is_from_user": True,
                    "date": fields.Datetime.now(),
                    "attachment_name": f"{self.name}.pdf",
                    "attachment_data": base64.b64encode(data),
                    "attachment_type": "doc",
                    }

                    chat_message = create_msg.create(vals)
                    print("chat_message..............",chat_message)       

                    
                except Exception as e:
                    pass    
                
                setting_object = self.env["ir.config_parameter"].sudo()
                url = setting_object.get_param("go4whatsapp_url")
                org_id = setting_object.get_param("org_id")
                mobile_no = f"{self.partner_id.mobile}"
                
                    # ✅ safely handle all cases   
                if order_values and isinstance(order_values, dict) and len(order_values) > 0:
                    variables_list = [
                        {"variableKey": k, "variableValue": (
                            v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v
                        )}
                        for k, v in order_values.items()
                    ]
                    variables_body = json.dumps(variables_list)
                else:
                    variables_list = []  # empty list if no data

                variables_body = json.dumps(variables_list)    
                ###################################################################
                try:
                    import requests
                    url = f"{url}/sendAttachmentWithVariableForOdoo"
                    payload = {'orgId': org_id,
                    'templateId': trigger.Whatsapp_template.template_id,
                    'mobileNo': mobile_no,
                    'variablesBody': f'{variables_body}'}

                    files=files
                    headers = {}
                    print("files.......",files)
                    print("................",variables_body)
                    print("response",payload)
                    response = requests.request("POST", url, headers=headers, data=payload, files=files)

                    channel = "RefreshwhatsappPage"
                    message= {"refresh": True}
                    datasets= self.env['bus.bus']._sendone(channel, 'Refresh_whatsapp_Page', message)

                    

                except Exception as e:
                    pass    
                #########################################################################

        return all_results

class AccountMove(models.Model):
    _inherit ="account.move"
    
    followup_date = fields.Date()
    
    def action_post(self):

        res = super(AccountMove, self).action_post()
        data=True
        # self.send_pdf_for_whatsapp()
        triger_state = None
        if self.move_type == 'out_invoice':
            print("➡️ Coming from: Customer Invoice section")
            if self.state == "draft":
                triger_state = "invoice_draft"
            elif self.state == "posted":
                triger_state = "invoice_payment"
            else:
                triger_state = "invoice_payment"
            # your WhatsApp logic

        elif self.move_type == 'in_invoice':
            print("➡️ Coming from: Vendor Bill section")
            if self.state == "draft":
                triger_state = "bill_draft"
            elif self.state == "posted":
                triger_state = "bill_payment"
            else:
                triger_state = "bill_posted"

        if triger_state:
            triggers = self.env['whatsapp.trigger'].search([
                ('model_id.model', '=', self._name),
                ('send_type', 'in', ['text', 'pdf','pdf-text']),
                ('trigger_state', '=', triger_state), 
                ('trigger_automatically','=',True)
            ])
            if triggers:
                self.send_pdf_for_whatsapp_on_web_side_account_move()
        return res
    
    def send_pdf_for_whatsapp(self):
        invoice_origin = self.invoice_origin  # e.g., SO123
        # Search for the sale order with matching name (invoice_origin)
        sale_order = self.env['sale.order'].search([('name', '=', invoice_origin)], limit=1)
        if sale_order:
            whatsapp_sale_order_id = sale_order.whatsapp_sale_order_id
            try:
                endpoint = "/sendDocumentINOddo"
                data = self.env['ir.actions.report'].sudo()._render_qweb_pdf('account.account_invoices', [self.id])[0]
                safe_filename = self.name.replace("/", "_") + ".pdf"
                # Get cross-platform temp directory (works on Linux and Windows)
                temp_dir = tempfile.gettempdir()
                print("code working....")
                # Full file path
                file_path = os.path.join(temp_dir, safe_filename)
                with open(file_path, 'wb') as file:
                    file.write(data)
                # Get the Go4Whatsapp URL from the configuration parameters
                setting_object = self.env["ir.config_parameter"].sudo()
                url = setting_object.get_param("go4whatsapp_url")+endpoint
                template_id = setting_object.get_param("template_id")
                org_id = setting_object.get_param("org_id")
                mobile_no = f"{self.partner_id.mobile}"

                invoice_origin = self.invoice_origin  # e.g., SO123
                # Search for the sale order with matching name (invoice_origin)
                sale_order = self.env['sale.order'].search([('name', '=', invoice_origin)], limit=1)
                if sale_order:
                    whatsapp_sale_order_id = sale_order.whatsapp_sale_order_id
                else:
                    whatsapp_sale_order_id = False

                if not self.partner_id.country_id:
                    raise UserError('Please select country from customer')
                
                if not self.partner_id.mobile:
                    raise UserError('Invalid Number')
                
                # Define headers with the access token for authorization
                headers = {
                    # 'Authorization': f'Bearer {self.env.user.go4whatsapp_access_token}',
                    # 'Content-Type': 'application/pdf'
                }

                files=[
                ('file',(f'{self.id}.pdf',open(file_path,'rb'),'application/pdf'))
                ]

                message = f'''
                    Hello {self.partner_id.name},\n We have successfully received your payment, \nYour order has been confirmed. Please find the Payment Invoice attached with this message.
                '''
                payload = {
                    "moNumber": mobile_no,
                    "templatedId": template_id,
                    "orgId": org_id,
                    "userName": self.partner_id.name,
                    "documentType": "text-pdf",
                    "filename":" Payment invoice.pdf",
                    "message":message,
                    "orderId": whatsapp_sale_order_id
                }
                response = requests.request("POST", url, headers=headers, data=payload, files=files)
                print("res..........",response.text)
                
                if response.status_code == 200:
                    print("File sent successfully.", response.json())
                else:
                    print("Failed to send file:", response.status_code, response.text)

            except Exception as e:
                pass
            
        else:
            print("not whatsapp order",self.state)
            pass
    
    # def write(self, vals):
    #     res = super(AccountMove, self).write(vals)

    #     # Use 'self' instead of 'res'
    #     triger_state = None
    #     if self.move_type == 'out_invoice':
    #         print("➡️ Coming from: Customer Invoice section")
    #         if self.state == "draft":
    #             triger_state = "invoice_draft"
    #         elif self.state == "posted":
    #             triger_state = "invoice_payment"
    #         else:
    #             triger_state = "invoice_payment"
    #         # your WhatsApp logic

    #     elif self.move_type == 'in_invoice':
    #         print("➡️ Coming from: Vendor Bill section")
    #         if self.state == "draft":
    #             triger_state = "bill_draft"
    #         elif self.state == "posted":
    #             triger_state = "bill_payment"
    #         else:
    #             triger_state = "bill_posted"

    #     if triger_state:
    #         triggers = self.env['whatsapp.trigger'].search([
    #             ('model_id.model', '=', self._name),
    #             ('send_type', 'in', ['text', 'pdf','pdf-text']),
    #             ('trigger_state', '=', triger_state), 
    #             ('trigger_automatically','=',True)
    #         ])
    #         if triggers:
    #             self.send_pdf_for_whatsapp_on_web_side_account_move()

    #     return res

    def send_pdf_for_whatsapp_on_web_side_account_move(self):

        check_subscription= self.env['whatsapp.payment.wizard'].check_subscription_expiration()
        if check_subscription == False:
             raise UserError("Your WhatsApp Connector monthly plan has expired.")

        print("send_pdf_for_whatsapp_on_web_side...", self._name,self.state)

        if self.move_type == 'out_invoice':
            print("➡️ Coming from: Customer Invoice section")
            if self.state == "draft":
                triger_state= "invoice_draft"
            elif self.state == "posted" :   
                triger_state= "invoice_payment" 
            else:
                triger_state= "invoice_payment"

        elif self.move_type == 'in_invoice':
            print("➡️ Coming from: Vendor Bill section")
            if self.state == "draft":
                triger_state= "bill_draft"
            elif self.state == "posted" :  
                triger_state= "bill_payment"  
            else:
                triger_state= "bill_posted"

        all_results = []
        order_values = {}
        if triger_state != None:
            # Filter whatsapp.trigger for current model & send_type = pdf
            triggers = self.env['whatsapp.trigger'].search([
                ('model_id.model', '=', self._name),
                ('send_type', 'in', ['text', 'pdf','pdf-text']),
                ('trigger_state', '=',triger_state )
            ])
            print("triggers....................",triggers)

            for trigger in triggers:
                trigger_data = trigger.read()[0]  # get all fields as dict
                trg_id=trigger_data["id"]
                fetch_fields = self.env['whatsapp.trigger.field.mapping'].search([
                ('trigger_id', '=', trg_id)
                ])

                if fetch_fields:
                    fetch_fields_data = fetch_fields.read(['model_field_id', 'template_field'])
                    print("fetch_fields_data...", fetch_fields_data)

                    for field_mapping in fetch_fields_data:
                        template_field = field_mapping.get('template_field')
                        model_field = field_mapping.get('model_field_id')

                        # Special case: username → partner name
                        if template_field == 'username' or template_field == 'name' :
                            order_values[template_field] = self.partner_id.name if self.partner_id else None
                            continue

                        # Normal case: get value from model_field_id
                        if model_field:
                            field_id = model_field[0]  # Many2one tuple
                            field_rec = self.env['ir.model.fields'].browse(field_id)
                            if field_rec and field_rec.name:
                                value = getattr(self, field_rec.name, False)
                                order_values[template_field] = value
                            else:
                                order_values[template_field] = None
                        else:
                            order_values[template_field] = None
                    print("...........",order_values)        

                else:
                    pass   

                try:

                    if trigger_data["send_type"] != "text":
                        data = self.env['ir.actions.report'].sudo()._render_qweb_pdf('account.account_invoices', [self.id])[0]
                        safe_filename = self.name.replace("/", "_") + ".pdf"
                        temp_dir = tempfile.gettempdir()
                        file_path = os.path.join(temp_dir, safe_filename)
                        print("file_path........",file_path)
                        with open(file_path, 'wb') as file:
                            file.write(data)
                        mime_type, _ = mimetypes.guess_type(file_path)
                        if mime_type != "application/pdf":
                            raise UserError("Generated file is not a valid PDF.")    

                        files=[('file',(safe_filename,open(file_path,'rb'),'application/pdf'))]

                        # PDF Chatter me attachment ke sath show
                        self.message_post(
                            body=f"A PDF {safe_filename} has been generated and sent to the customer.",
                            attachments=[(
                                {safe_filename},
                                data
                            )]
                        )   

                    else:
                       files=[] 

                except Exception as e:
                    pass    

                setting_object = self.env["ir.config_parameter"].sudo()
                url = setting_object.get_param("go4whatsapp_url")
                org_id = setting_object.get_param("org_id")
                mobile_no = f"{self.partner_id.mobile}"
                
                    # safely handle all cases
                print("order_values.....",order_values)    
                if order_values and isinstance(order_values, dict) and len(order_values) > 0:
                    variables_list = [
                        {"variableKey": k, "variableValue": (
                            v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v
                        )}
                        for k, v in order_values.items()
                    ]
                    variables_body = json.dumps(variables_list)
                else:
                    variables_list = []  # empty list if no data

                variables_body = json.dumps(variables_list)   
                print("....",variables_body) 
                ###################################################################
                try:
                    import requests
                    url = f"{url}/sendAttachmentWithVariableForOdoo"
                    payload = {'orgId': org_id,
                    'templateId': trigger.Whatsapp_template.template_id,
                    'mobileNo': mobile_no,
                    'variablesBody': f'{variables_body}'}

                    files=files
                    print("files.......",files)
                    print("................",variables_body)
                    print("response",payload)
                    headers = {}
                    response = requests.request("POST", url, headers=headers, data=payload, files=files)
                    print("response...............",response)
                except Exception as e:
                    pass    

                #########################################################################

        return all_results

class PurchaseOrder(models.Model):
    
    _inherit ="purchase.order"


    @api.model
    def create(self, vals):
        record = super(PurchaseOrder, self).create(vals)
        # Example: print or log
        print(".....Purchase order created.....", record.name, record.state)
        return record
    

    def write(self, vals):
        if self.env.context.get('state_change_handled'):
            return super(PurchaseOrder, self).write(vals)

        old_states = {rec.id: rec.state for rec in self}

        res = super(PurchaseOrder, self.with_context(state_change_handled=True)).write(vals)

        for record in self:
            old_state = old_states.get(record.id)
            new_state = record.state

            if old_state != new_state:
                print(f" State changed for {record.name}: {old_state} → {new_state}")

                # Trigger state mapping
                if new_state == "draft":
                    trigger_state = "purchase_draft"
                elif new_state == "sent":
                    trigger_state = "purchase_sent"
                elif new_state == "purchase":
                    trigger_state = "purchase_confirmed"
                elif new_state == "cancel":
                    trigger_state = "purchase_cancel"
                else:
                    trigger_state = None

                if trigger_state:
                    triggers = record.env['whatsapp.trigger'].search([
                        ('model_id.model', '=', record._name),
                        ('send_type', 'in', ['text', 'pdf', 'pdf-text']),
                        ('trigger_state', '=', trigger_state),
                        ('trigger_automatically', '=', True)
                    ])
                    if triggers:
                        record.send_pdf_for_whatsapp_on_web_side()
                        print(f" WhatsApp trigger fired for {record.name} ({trigger_state})")

        return res



    def send_pdf_for_whatsapp_on_web_side(self): 

        check_subscription= self.env['whatsapp.payment.wizard'].check_subscription_expiration()
        if check_subscription == False:
             raise UserError("Your WhatsApp Connector monthly plan has expired.")

        print("........purchase order ................", self._name,self.state)

        if self.state == "draft":
            triger_state= "purchase_draft"
        elif self.state == "sent" :  
            triger_state= "purchase_sent" 
        elif self.state =="purchase":
            triger_state= "purchase_confirmed"  
        elif self.state =="cancel":
            triger_state= "purchase_cancel"  
        else:
            triger_state=None    

        all_results = []
        order_values = {}
        
        if triger_state != None:

            triggers = self.env['whatsapp.trigger'].search([
                ('model_id.model', '=', self._name),
                ('send_type', 'in', ['text', 'pdf','pdf-text']),
                ('trigger_state', '=',triger_state )
            ])

            for trigger in triggers:

                trigger_data = trigger.read()[0]  # get all fields as dict
                trg_id=trigger_data["id"]
                fetch_fields = self.env['whatsapp.trigger.field.mapping'].search([
                ('trigger_id', '=', trg_id)
                ])

                if fetch_fields:
                    fetch_fields_data = fetch_fields.read(['model_field_id', 'template_field'])
                    print("fetch_fields_data...", fetch_fields_data)

                    for field_mapping in fetch_fields_data:
                        template_field = field_mapping.get('template_field')
                        model_field = field_mapping.get('model_field_id')

                        # Special case: username → partner name
                        if template_field == 'username':
                            order_values[template_field] = self.partner_id.name if self.partner_id else None
                            continue

                        # Normal case: get value from model_field_id
                        if model_field:
                            field_id = model_field[0]  # Many2one tuple
                            field_rec = self.env['ir.model.fields'].browse(field_id)
                            if field_rec and field_rec.name:
                                value = getattr(self, field_rec.name, False)
                                order_values[template_field] = value
                            else:
                                order_values[template_field] = None
                        else:
                            order_values[template_field] = None
                    print("...........",order_values)        

                else:
                    pass   

                try:
                    if trigger_data["send_type"] != "text":
                        # Purchase Order report ka QWeb template ID
                        data = self.env['ir.actions.report'].sudo()._render_qweb_pdf('purchase.report_purchaseorder', [self.id])[0]
                        # File name setup
                        safe_filename = self.name.replace("/", "_") + ".pdf"
                        temp_dir = tempfile.gettempdir()
                        file_path = os.path.join(temp_dir, safe_filename)
                        # Write PDF to temporary file
                        with open(file_path, 'wb') as file:
                            file.write(data)
                        # Validate MIME type
                        mime_type, _ = mimetypes.guess_type(file_path)
                        if mime_type != "application/pdf":
                            raise UserError("Generated file is not a valid PDF.")
                        # Prepare file for sending (e.g., WhatsApp API)
                        files = [('file', (f'{self.name}.pdf', open(file_path, 'rb'), 'application/pdf'))]

                        # PDF Chatter me attachment ke sath show
                        self.message_post(
                            body=f"A PDF {self.name}.pdf has been generated and sent to the customer.",
                            attachments=[(
                               f"{self.name}.pdf",
                                data
                            )]
                        )   
                    else:
                        files = []

                except Exception as e:
                    pass

                setting_object = self.env["ir.config_parameter"].sudo()
                url = setting_object.get_param("go4whatsapp_url")
                org_id = setting_object.get_param("org_id")
                mobile_no = f"{self.partner_id.mobile}"
                
                    # ✅ safely handle all cases
                if order_values and isinstance(order_values, dict) and len(order_values) > 0:
                    variables_list = [
                        {"variableKey": k, "variableValue": (
                            v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v
                        )}
                        for k, v in order_values.items()
                    ]
                    variables_body = json.dumps(variables_list)
                else:
                    variables_list = []  # empty list if no data

                variables_body = json.dumps(variables_list)    
                ###################################################################
                try:
                    import requests
                    url = f"{url}/sendAttachmentWithVariableForOdoo"
                    payload = {'orgId': org_id,
                    'templateId': trigger.Whatsapp_template.template_id,
                    'mobileNo': mobile_no,
                    'variablesBody': f'{variables_body}'}
                    files=files
                    headers = {}
                    response = requests.request("POST", url, headers=headers, data=payload, files=files)
                    print(response)
                except Exception as e:
                    pass    

                #########################################################################

        return all_results

class ResUsers(models.Model):
    _inherit = "res.users"
    
    go4whatsapp_access_token = fields.Text()

    def open_whatsapp_login_form(self):
        
        return {
            'name': 'Go4Whatsapp Login',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'whatsapp.login',
            'target' : 'new'
        }
            
class LoginGo4Whatsapp(models.TransientModel):
    _name = "whatsapp.login"
    
    mobileNo = fields.Char(string="Mobile Number")
    isSocial = fields.Boolean(string="Is Socail")
    email = fields.Char(string="Email")
    
    def action_open_registration(self):
        import pip
        try:
            import jwt
        except ImportError:
            pip.main(['install', 'jwt'])
        import datetime

        """ Redirects to the registration page with a JWT token """
        secret_key = "OdooSecretKey"  # Replace with actual secret key
        payload = {
            "key": "OdooLead",
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }
        token = jwt.encode(payload, secret_key, algorithm="HS256")

        base_url = "https://app.go4whatsup.com/registration"
        url = f"{base_url}?token={token}"

        return {
            "type": "ir.actions.act_url",
            "target": "new",
            "url": url
        }
    
    def open_otp_verify_form(self):
        
        url = f'{self.env["ir.config_parameter"].sudo().get_param("go4whatsapp_url")}/oddoSignInUser'
        payload = {"mobileNo":self.mobileNo, "isSocial": False, "email": self.email}
        response = requests.post(url, data=payload)
        
        if response.json().get("ErrorCode") == 200:
            self.env.user.mobile = self.mobileNo
            return {
                'name': 'OTP Verify',
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'otp.verify',
                'context': {'default_mobileNo': self.mobileNo},
                'target' : 'new'
            }
        else:
            raise UserError(response.json().get("ErrorMessage"))
            
class OTPVerify(models.TransientModel):
    _name = "otp.verify"
    
    mobileNo = fields.Char(string="Mobile Number", required=True)
    otp = fields.Char(string="OTP", required=True)
    
    def set_user_access_token(self):
        
        url = f'{self.env["ir.config_parameter"].sudo().get_param("go4whatsapp_url")}/oddoVerifyOtp'
        payload = {"mobileNo": self.mobileNo, "otp":self.otp}
        response = requests.post(url, data=payload)

        if response.json().get("ErrorCode") == 200:
            self.env.user.go4whatsapp_access_token = response.json().get("VerifyOtp").get("authtoken")
            self.env['ir.config_parameter'].sudo().set_param('org_id',response.json().get("VerifyOtp", {}).get("userDetail", [{}])[0].get("orgId"))

            self.env['ir.config_parameter'].sudo().set_param('template_id',response.json().get("VerifyOtp").get("send_odooinvoice_marketingTemplateId",'676a8bd7773ff7359741c764'))
            self.env['ir.config_parameter'].sudo().set_param('shippingTemplatedId',response.json().get("VerifyOtp").get("shippingTemplatedId"))
            self.env['ir.config_parameter'].sudo().set_param('apikey',response.json().get("VerifyOtp").get("apikey"))
            self.env['ir.config_parameter'].sudo().set_param('secureKey',response.json().get("VerifyOtp").get("secureKey"))
            self.env['ir.config_parameter'].sudo().set_param('go4whatsapp_access_token',response.json().get("VerifyOtp").get("authtoken"))
        
            url = f'{self.env["ir.config_parameter"].sudo().get_param("go4whatsapp_url")}/getCurentPlanDetailByOrg'

            payload = json.dumps({
            "orgId": self.env["ir.config_parameter"].sudo().get_param("org_id")
            })
            headers = {
            'authorization': response.json().get("VerifyOtp").get("authtoken"),
            'Content-Type': 'application/json',
            'Cookie': 'HttpOnly'
            }

            response = requests.request("POST", url, headers=headers, data=payload)

            expiry_date_str = response.json().get("getCurentPlanDetailByuser")[0]["expiryDate"]

            # Convert to date object
            expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%dT%H:%M:%S.%fZ").date()

            # Store in system parameter
            self.env['ir.config_parameter'].sudo().set_param('Subscription_expire_date', expiry_date.isoformat())
            self.env['ir.config_parameter'].sudo().set_param('odoo_expire_date', date.today() + timedelta(days=365))

            return {
                'effect': {
                    'fadeout': 'slow',
                    'message': 'Login is confirmed',
                    'type': 'rainbow_man',
                    }
                }
        else:
            raise UserError(response.json().get("ErrorMessage"))
        
class MrpBomLine(models.Model):
    _inherit = 'mrp.bom.line'

    free_qty = fields.Char(string="Free qty")
    unit_price = fields.Char(string="Unit price")            

class ProductInherit(models.Model):
    _inherit = "product.template"

    Product_sku_id = fields.Char(string='SKU Id', size=200, help="META product SKU Id" ,null=True)
    arabic_name = fields.Char(string='arabic name', size=200, help="arabic name of combo" ,null=True)

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    combo_product_name = fields.Char(string="Combo Product")
    custom_code = fields.Char(string="Combo Product", readonly=True)

class StockMove(models.Model):
    _inherit = 'stock.move'

    custom_code = fields.Char(string="Combo Product", readonly=True) 
    combo_product_name = fields.Char(string="Combo Product", related='sale_line_id.combo_product_name', store=True)

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    combo_product_name = fields.Char(string="Combo Product", readonly=True)  
    custom_code = fields.Char(string="Combo Product", readonly=True)

class ModuleName(models.Model):
    _name = 'module.name'
    _description = 'Module Name Table'

    name = fields.Char(string='Module Name', required=True)
    model_db_name = fields.Many2one(
        comodel_name='ir.model',
        string="Model Name",
        required=False,
        ondelete='set null'
    )
    trigger_point_ids = fields.One2many(
        comodel_name='module.trigger.point',
        inverse_name='module_id',
        string='Trigger Points'
    )

class ModuleTriggerPoint(models.Model):
    _name = 'module.trigger.point'
    _description = 'Module Trigger Point Table'

    name = fields.Char(string='Trigger Point', required=True)
    description = fields.Char(string='Trigger Point description')
    module_id = fields.Many2one(
        comodel_name='module.name',
        string='Module',
        ondelete='cascade'
    )

class SetTriggerPoint(models.Model):
    _name = 'set.trigger.point'
    _description = 'Set Trigger Point Table'

    name = fields.Char(string="Name", required=True)

    module_name_id = fields.Many2one(
        comodel_name='module.name',
        string="Module Name",
        required=True,
        ondelete="cascade"
    )

    # Multiple field selection from chosen module model
    field_selection = fields.Many2many(
        comodel_name='ir.model.fields',
        string="Fields",
        domain="[('model_id','=',model_db_name)]"
    )

    trigger_point_id = fields.Many2one(
        comodel_name='module.trigger.point',
        string="Trigger Point",
        required=True,
        domain="[('module_id','=',module_name_id)]"
    )

    header_type = fields.Selection(
        [
            ('text', 'Text'),
            ('document', 'Document'),
            ('link', 'Link'),
        ],
        string="Header Type",
        required=True
    )

    template_id = fields.Many2one(
        comodel_name='mail.template',
        string="Template"
    )

    # helper: get model_db_name from module
    model_db_name = fields.Many2one(
        comodel_name="ir.model",
        string="Related Model",
        related="module_name_id.model_db_name",
        store=True,
        readonly=True
    )

class WhatsAppTrigger(models.Model):
    _name = "whatsapp.trigger"
    _description = "WhatsApp Trigger"

    name = fields.Char("Trigger Name", required=True,help="Enter a unique name for this WhatsApp trigger rule.")
    active = fields.Boolean("Active", default=True,help="If unchecked, this trigger will be disabled and not executed.")

    model_id = fields.Many2one(
        'ir.model',
        string="Odoo Model",
        required=True,
        ondelete='cascade',
        domain="[('model', 'in', ['sale.order', 'purchase.order','stock.picking' ,'pos.order','account.move'])]",
        help="Select the Odoo model for which this trigger should apply."
    )

    send_type = fields.Selection([
        ("text", "Text"),
        ("pdf", "PDF"),
        ("pdf-text", "PDF-Text"),
        ("link", "Link")
    ], string="Send As", required=True,help="Choose how the WhatsApp message should be sent — as text, PDF, both, or a link.")

    #  Unique keys so ALL show in dropdown
    trigger_state = fields.Selection([
        ('sale_draft', 'Draft Quotation Send'),
        ('sale_sent', 'Quotation Sent'),
        ('sale_confirmed', 'Sales Order Send'),
        ('sale_cancel', 'Cancelled Order Send'),

        ('invoice_draft', 'Draft Invoice Send'),
        ('invoice_posted', 'Posted Invocie Send'),
        ('invoice_payment', 'Payment Invoice Send'),

        ('delivery_in_draft', 'Draft delivery status send'),
        ('delivery_in_assigned', 'Ready for Delivery'),
        ('delivery_in_done', 'Order Delivered'),

        ('purchase_draft', 'Draft Purchase Order Send'),
        ('purchase_sent', 'Purchase Order Sent'),
        ('purchase_confirmed', 'Purchase Order Confirmation'),
        ('purchase_cancel', 'Purchase Order Cancelled'),

        ('bill_draft', 'Draft Bill Send'),
        ('bill_posted', 'Posted Bill Send'),
        ('bill_payment', 'Payment Bill Send'),

        ('pos_bill', 'Send POS unpaid Bill on whatsapp'),
        ('pos_payment_slip', 'Send POS Paid Bill on whatsapp'),
    ], string="Trigger State",help="Select the system event that will trigger the WhatsApp message.")

    Whatsapp_template = fields.Many2one(
        comodel_name="whatsapp.template",
        string="Whatsapp Template",help="Select the WhatsApp template to use for this trigger."
    )
    #  Add this new One2many to hold mappings
    field_mapping_ids = fields.One2many(
        'whatsapp.trigger.field.mapping',
        'trigger_id',
        string="Field Mappings",
         help="Define which fields from the Odoo model should map to WhatsApp template variables."
    )

    trigger_automatically = fields.Boolean(string="Trigger Automatically",help="Set field TRUE if you want to send template on trigger point Automatically.")

    @api.onchange('Whatsapp_template')
    def _onchange_trigger_state(self):
        """Extract example fields and populate mapping lines"""
        self.field_mapping_ids = [(5, 0, 0)]  # always clear old lines first

        if not self.Whatsapp_template or not self.Whatsapp_template.components_json:
            return

        import json, logging
        _logger = logging.getLogger(__name__)

        try:
            data = json.loads(self.Whatsapp_template.components_json)
            _logger.info("Parsed template JSON: %s", data)
        except Exception as e:
            _logger.error("JSON Parse Error: %s", e)
            return

        body_item = next((item for item in data if item.get("type") == "BODY"), None)
        if not body_item:
            _logger.warning("No BODY item found in template.")
            return

        if "example" in body_item:
            example_fields = body_item["example"]["body_text"][0]
            _logger.info("Extracted example fields: %s", example_fields)

            self.field_mapping_ids = [(0, 0, {'template_field': f}) for f in example_fields]
        else:
            _logger.warning("No 'example' key found in BODY item.")
            
class WhatsAppTriggerFieldMapping(models.Model):
    _name = "whatsapp.trigger.field.mapping"
    _description = "Mapping between Template Field and Model Field"

    trigger_id = fields.Many2one('whatsapp.trigger', string="Trigger", ondelete='cascade')
    template_field = fields.Char("Template Field")

    model_field_id = fields.Many2one(
        'ir.model.fields',
        string="Model Field",
        domain="[('model_id', '=', parent.model_id)]"
    )

    field_path = fields.Char("Field Path (e.g. partner_id.name)")

class WhatsApptemplate(models.Model):
    _name = "whatsapp.template"
    _description = "WhatsApp Template"
    _rec_name = "template_name"
    _order = "create_date desc"

    template_id = fields.Char("WhatsApp Template ID",readonly=True) 
    org_id = fields.Char(
        string="Organization ID",
        readonly=True,
        default=lambda self: self.env['ir.config_parameter']
            .sudo()
            .get_param('org_id')
    )
    template_name = fields.Char("Template Name")
    status = fields.Selection(
        [
            ('PENDING', 'PENDING'),
            ('APPROVED', 'APPROVED'),
            ('REJECTED', 'REJECTED'),
        ],
        string="Status",
        default='PENDING',
        readonly=True
    )
    is_active = fields.Boolean("Is Active", default=True)
    is_delete = fields.Boolean("Is Deleted", default=False)
    is_verified = fields.Boolean("Is Verified", default=False)
    template_utility = fields.Char("Template Utility")
    is_display = fields.Boolean("Is Display", default=True)
    created_at = fields.Datetime("Created At")
    category01 = fields.Selection(
        [
            ('utility', 'Utility'),
            ('marketing', 'Marketing'),
            ('authentication', 'Authentication'),
        ],
        default='marketing',
        required=True
    )
    language = fields.Selection(
        [
            ('af', 'Afrikaans'),
            ('sq', 'Albanian'),
            ('ar', 'Arabic'),
            ('az', 'Azerbaijani'),
            ('bn', 'Bengali'),
            ('bg', 'Bulgarian'),
            ('ca', 'Catalan'),
            ('zh_CN', 'Chinese (CHN)'),
            ('zh_HK', 'Chinese (HKG)'),
            ('zh_TW', 'Chinese (TAI)'),
            ('hr', 'Croatian'),
            ('cs', 'Czech'),
            ('da', 'Danish'),
            ('nl', 'Dutch'),
            ('en', 'English'),
            ('en_GB', 'English (UK)'),
            ('en_US', 'English (US)'),
            ('et', 'Estonian'),
            ('fil', 'Filipino'),
            ('fi', 'Finnish'),
            ('fr', 'French'),
            ('de', 'German'),
            ('el', 'Greek'),
            ('gu', 'Gujarati'),
            ('ha', 'Hausa'),
            ('he', 'Hebrew'),
            ('hi', 'Hindi'),
            ('hu', 'Hungarian'),
            ('id', 'Indonesian'),
            ('ga', 'Irish'),
            ('it', 'Italian'),
            ('ja', 'Japanese'),
            ('kn', 'Kannada'),
            ('kk', 'Kazakh'),
            ('ko', 'Korean'),
            ('lo', 'Lao'),
            ('lv', 'Latvian'),
            ('lt', 'Lithuanian'),
            ('mk', 'Macedonian'),
            ('ms', 'Malay'),
            ('ml', 'Malayalam'),
            ('mr', 'Marathi'),
            ('nb', 'Norwegian'),
            ('fa', 'Persian'),
            ('pl', 'Polish'),
            ('pt_BR', 'Portuguese (BR)'),
            ('pt_PT', 'Portuguese (POR)'),
            ('pa', 'Punjabi'),
            ('ro', 'Romanian'),
            ('ru', 'Russian'),
            ('sr', 'Serbian'),
            ('sk', 'Slovak'),
            ('sl', 'Slovenian'),
            ('es', 'Spanish'),
            ('es_AR', 'Spanish (ARG)'),
            ('es_ES', 'Spanish (SPA)'),
            ('es_MX', 'Spanish (MEX)'),
            ('sw', 'Swahili'),
            ('sv', 'Swedish'),
            ('ta', 'Tamil'),
            ('te', 'Telugu'),
            ('th', 'Thai'),
            ('tr', 'Turkish'),
            ('uk', 'Ukrainian'),
            ('ur', 'Urdu'),
            ('uz', 'Uzbek'),
            ('vi', 'Vietnamese'),
            ('zu', 'Zulu'),
        ],
        string='Language',
        required=True
    )
    template_type = fields.Selection(
        [
            ('normal', 'Normal'),
            ('enquiry', 'Enquiry'),
        ],
        string='Template Type',
        required=True
    )
    header_type = fields.Selection(
        [
            ('text', 'Text'),
            ('image', 'Image'),
            ('document', 'Document'),
            ('video', 'Video'),
        ],
        string='Header Type',
        
    )

    body_text = fields.Text("Body Text")
    footer_text = fields.Text("Footer Text", default="Please reply with 'STOP' to opt-out" )
    header_image = fields.Char("Header Image / Document / Media URL")
    first_quick_button = fields.Char("First Quick Button")
    second_quick_button = fields.Char("Second Quick Button")
    third_quick_button = fields.Char("Third Quick Button")
    quick_btn_length = fields.Integer("Quick Button Length")
    btn_url_text = fields.Char("Button URL Text")
    btn_phone_number_text = fields.Char("Button Phone Text")
    template_design_json = fields.Text("Template Design JSON")
    templated_object_json = fields.Text("Templated Object JSON")
    components_json = fields.Text("Components JSON")
    extra_object_json = fields.Text("Extra Object JSON")
    component_body_text = fields.Text("Component Body Text")
    component_footer_text = fields.Text("Component Footer Text")
    component_buttons_json = fields.Text("Component Buttons JSON")
    component_header_json = fields.Text("Component Header JSON")
    templated_keyword_datas = fields.Text("Templated Keyword Data JSON")
    remarks = fields.Text("Remarks / Notes")
    message_preview = fields.Html("Message Preview", compute="_compute_message_preview", sanitize=False)
    header_media_file = fields.Binary("Media File", attachment=True)
    header_filename = fields.Char("File Name")
    otp_expiry = fields.Selection(
        [(str(i), f"{i} Minutes") for i in range(1, 21)],
        string="OTP Expiry Time",
        default="1"
        )
    send_footer = fields.Boolean(
        string="Send Footer",
        default=True
    )
    button_type = fields.Selection([
        ('none', 'None'),
        ('cta', 'Call To Action'),
        ('quick', 'Quick Reply'),
    ], default='none', string="Add Call to Action Buttons")
    # Call button

    country_id = fields.Many2one(
        "res.country",
        string="Country"
    )

    country_code = fields.Char(
        string="Country Code",
        compute="_compute_country_code",
        store=True
    )

    cta_call_text = fields.Char(string="Button name")
    cta_call_number = fields.Char(string="Add Number")
    cta_call_enabled = fields.Boolean(default=False,string="Add contact Button")

    # Website button
    cta_url_text = fields.Char(string="Button name")
    cta_url = fields.Char(string="Add Website url")
    cta_url_enabled = fields.Boolean(default=False,string="Add Website Button")


    variable_ids = fields.One2many(
        'whatsapp.template.variable',
        'template_id',
        string='Variables'
    )

    @api.depends("country_id")
    def _compute_country_code(self):
        for rec in self:
            if rec.country_id and rec.country_id.phone_code:
                rec.country_code = f"+{rec.country_id.phone_code}"
            else:
                rec.country_code = ""
 
    def _prepare_body_and_examples(self):
        body = self.body_text or ""
        example_values = []

        for index, var in enumerate(self.variable_ids.sorted('sequence'), start=1):
            value = self._resolve_variable_value(var)

            body = body.replace(f"{{{{{index}}}}}", value)
            example_values.append(value)

        return body, example_values
    
    def _resolve_variable_value(self, var):
        if var.variable_type == 'custom':
            return var.custom_value or ''
        elif var.variable_type == 'user_name':
            return 'name'
        elif var.variable_type == 'current_date':
            return date.today().strftime('%Y-%m-%d')
        return ''
    
    def action_create_template_on_meta(self):
        self.ensure_one()
        check_subscription= self.env['whatsapp.payment.wizard'].check_subscription_expiration()
        print("check_subscription.............",check_subscription)
        if check_subscription == False:
            ICP = self.env["ir.config_parameter"].sudo()
            payment_link = ICP.get_param("payment_link")
            return {
                    'type': 'ir.actions.act_window',
                    'name': 'Plan Expired',
                    'res_model': 'payment.confirm.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'payment_url': payment_link,
                        'default_apply_free_trial_plan': False,
                    }
                }

        setting = self.env['ir.config_parameter'].sudo()
        base_url = setting.get_param("go4whatsapp_url")
        org_id = setting.get_param("org_id")
        apikey = setting.get_param("apikey")
        secureKey = setting.get_param("secureKey")

        url = f"{base_url}/developerApi/createTemplate/v1/{apikey}/{secureKey}"

        final_body, example_list = self._prepare_body_and_examples()
        components = []

        # ==================================================
        # AUTHENTICATION TEMPLATE (SPECIAL PAYLOAD)
        # ==================================================
        if self.category01 == 'authentication':

            # BODY (no text, only security recommendation)
            components.append({
                "type": "BODY",
                "add_security_recommendation": True
            })

            # OTP BUTTON (mandatory)
            components.append({
                "type": "BUTTONS",
                "buttons": [{
                    "type": "otp",
                    "otp_type": "one_tap",
                    "supported_apps": [{
                        "package_name": "com.example.luckyshrub",
                        "signature_hash": "K8a/AINcGX7"
                    }]
                }]
            })

            # FOOTER (only if enabled)
            if self.send_footer and self.otp_expiry:
                components.append({
                    "type": "FOOTER",
                    "code_expiration_minutes": self.otp_expiry
                })

            template_design = {
                "orgId": org_id,
                "language": self.language,
                "category": "AUTHENTICATION",
                "body_text": (
                    "{{1}} is your verification code. "
                    "For your security, do not share this code."
                ),
                "footer_text": (
                    f"This code expire in {self.otp_expiry} minutes."
                    if self.send_footer else ""
                )
            }

            button_caption = json.dumps("Copy code")

        # ==================================================
        # NORMAL / MARKETING TEMPLATE (EXISTING LOGIC)
        # ==================================================


        else:
            # HEADER
            if self.header_type:
                header = {
                    "type": "HEADER",
                    "format": self.header_type.upper()
                }
                if self.header_type == 'document':
                    header["document"] = {"link": {}}
                components.append(header)

            # BODY
            body_component = {
                "type": "BODY",
                "text": self.body_text or ""
            }
            if example_list:
                body_component["example"] = {"body_text": example_list}
            components.append(body_component)

            # FOOTER
            if self.footer_text:
                components.append({
                    "type": "FOOTER",
                    "text": self.footer_text
                })

            buttons = []

            # CALL BUTTON
            if self.cta_call_enabled:
                buttons.append({
                    "type": "PHONE_NUMBER",
                    "text": self.cta_call_text or "Call us",
                    "phone_number": self.cta_call_number
                })

            # WEBSITE BUTTON
            if self.cta_url_enabled:
                buttons.append({
                    "type": "URL",
                    "text": self.cta_url_text or "Visit website",
                    "url": self.cta_url
                })

            # Only add BUTTONS component if at least one button exists
            if buttons:
                components.append({
                    "type": "BUTTONS",
                    "buttons": buttons
                })

            template_design = {
                "orgId": org_id,
                "language": self.language,
                "category": self.category01.upper(),
                "header_type": self.header_type,
                "body_text": final_body,
                "footer_text": self.footer_text or ""
            }

            if self.cta_call_enabled:
                template_design["btnPhoneNumberText"] = self.cta_call_text or ""

            if self.cta_url_enabled:
                template_design["btnUrlText"] = self.cta_url_text or ""

            button_caption_list = []

            if self.cta_call_enabled and self.cta_call_text:
                button_caption_list.append(self.cta_call_text)

            if self.cta_url_enabled and self.cta_url_text:
                button_caption_list.append(self.cta_url_text)

            button_caption= json.dumps(button_caption_list)    

        # ==================================================
        # FINAL PAYLOAD
        # ==================================================
        payload = {
            'orgId': org_id,
            'name': self.template_name,
            'language': self.language,
            'isNormalTemplate': '1',
            'category': self.category01.upper(),
            'countryCode': 'undefined',
            'templateType': self.template_type,
            'templateUtility': '',
            'extraObject': json.dumps([{"slotname": ""}]),
            'components': json.dumps(components),
            'templateDesign': json.dumps(template_design),
            "buttonCaption": button_caption
        }

        files = []
        if self.header_media_file and self.header_filename:
            files.append((
                'link',
                (
                    self.header_filename,
                    base64.b64decode(self.header_media_file),
                    'application/pdf'
                )
            ))

        try:
            print("payload.......",payload)
            response = requests.post(
                url,
                data=payload,
                files=files or None,
                timeout=30
            )

            try:
                resp_json = response.json()
                print("resp_json.......",resp_json)
            except Exception:
                resp_json = {}

            if response.status_code != 200:
                error_msg = (
                    resp_json.get('ErrorMessage')
                    or resp_json.get('error')
                    or resp_json.get('message')
                    or response.text
                )

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'WhatsApp API Error',
                        'message': error_msg,
                        'type': 'danger',
                        'sticky': True,
                    }
                }

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success',
                    'message': 'Template sent to Meta successfully',
                    'type': 'success',
                }
            }

        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'System Error',
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }


    def Check_template_status(self):
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()

        base_url = ICP.get_param('web.base.url')

        if not base_url:
            raise UserError("Go4Whatsapp URL is not configured")

        url = base_url.rstrip('/') + "/TemplateWebhook"

        response = requests.post(
            url,
            json={},
            timeout=10
        )
        
        return True

    def action_add_variable(self):
        self.ensure_one()

        next_seq = len(self.variable_ids) + 1
        variable_key = f'{{{{{next_seq}}}}}'

        # body me add karo
        if self.body_text:
            self.body_text += f' {variable_key}'
        else:
            self.body_text = f'Hello {variable_key}'

        # mapping row create karo
        self.env['whatsapp.template.variable'].create({
            'template_id': self.id,
            'sequence': next_seq,
            'key': variable_key,
        })

    @api.model
    def action_sync_templates(self):
        pass
    
    @api.model
    def create(self, vals):
        if vals.get('category01') == 'authentication':
            expiry = vals.get('otp_expiry') or '1'

            vals['body_text'] = (
                "{{1}} is your verification code. "
                "For your security, do not share this code."
            )

            if vals.get('send_footer', True):
                vals['footer_text'] = f"This code expires in {expiry} minutes."

            # variable auto-create
            vals['variable_ids'] = [(0, 0, {
                'sequence': 1,
                'key': "{{1}}",
                'variable_type': 'custom',
                'custom_value': '1234',
            })]

        return super().create(vals)

    @api.onchange('category01', 'otp_expiry', 'send_footer')
    def _onchange_authentication_template(self):
        if self.category01 == 'authentication':
            expiry = self.otp_expiry or '1'

            # BODY (always)
            self.body_text = (
                "{{1}} is your verification code. "
                "For your security, do not share this code."
            )

            # FOOTER (only if checkbox ticked)
            if self.send_footer:
                self.footer_text = f"This code expires in {expiry} minutes."
            else:
                self.footer_text = False

            # only one variable
            if not self.variable_ids:
                self.variable_ids = [(0, 0, {
                    'sequence': "1",
                    'key': "{{1}}",
                    'variable_type': 'custom',
                    'custom_value': '1234',
                })]
        else:
            self.body_text = False
            self.footer_text = "Please reply with 'STOP' to opt-out."
            self.send_footer = True
            self.variable_ids = [(5, 0, 0)]

    @api.depends("body_text", "footer_text", "header_image", "header_media_file", "header_filename", "template_name","cta_call_enabled","cta_url_enabled","cta_call_text","cta_url_text")
    def _compute_message_preview(self):
        for record in self:
            # --- Media / Attachment preview ---
            media_html = ""
            file_url = None
            file_name = "Document"

            if record.header_image:
                file_url = record.header_image
                file_name = os.path.basename(record.header_image)
                mime_type, _ = mimetypes.guess_type(file_url)

            elif record.header_media_file:
                file_name = record.header_filename or "Document"
                file_url = f"/web/content/{record._name}/{record.id}/header_media_file/{file_name}"
                mime_type, _ = mimetypes.guess_type(file_name)

            if file_url:
                file_url_lower = file_url.lower()

                # IMAGE
                if (mime_type and mime_type.startswith("image")) or file_url_lower.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                    media_html = f"""
                        <div style="border-radius:8px;overflow:hidden;margin-bottom:6px;">
                            <img src="{file_url}" style="width:100%;border-radius:8px;">
                        </div>
                    """

                # DOCUMENT
                elif file_url_lower.endswith((".pdf", ".doc", ".docx")):
                    media_html = f"""
                        <div style="
                            background:#f0f0f0;
                            border-radius:8px;
                            padding:15px 10px;
                            border:1px solid #ddd;
                            text-align:center;
                            margin-bottom:6px;
                        ">
                            <div style="font-size:40px;color:#999;">📄</div>
                            <div style="color:#25D366;font-weight:600;font-size:13px;">Download</div>
                            <div style="font-size:12px;color:#444;">{file_name or 'Document'}</div>
                        </div>
                    """

                # VIDEO (NEW)
                elif mime_type and mime_type.startswith("video"):
                    media_html = f"""
                        <video controls style="width:100%;border-radius:8px;margin-bottom:6px;">
                            <source src="{file_url}">
                        </video>
                    """

            # --- Chat bubble with <pre> preserving formatting ---

            buttons_html = ""

            if record.cta_call_enabled:
                buttons_html += f"""
                    <div style="
                        margin-top:6px;
                        padding:8px;
                        border:1px solid #ddd;
                        border-radius:20px;
                        text-align:center;
                        background:#fff;
                        font-size:13px;
                        color:#075e55;
                        cursor:pointer;
                    ">
                        📞 {record.cta_call_text or 'Call me'}
                    </div>
                """

            if record.cta_url_enabled:
                buttons_html += f"""
                    <div style="
                        margin-top:6px;
                        padding:8px;
                        border:1px solid #ddd;
                        border-radius:20px;
                        text-align:center;
                        background:#fff;
                        font-size:13px;
                        color:#075e55;
                        cursor:pointer;
                    ">
                        🔗 {record.cta_url_text or 'Visit website'}
                    </div>
                """
            chat_bubble = f"""
                <div style="
                    background:#dcf8c6;
                    border-radius:8px;
                    padding:8px 12px;
                    display:inline-block;
                    max-width:85%;
                    font-size:13px;
                    color:#222;
                    box-shadow:0 1px 2px rgba(0,0,0,0.1);
                    align-self:flex-end;
                    text-align:left;
                    word-wrap:break-word;
                    line-height:1.4;
                    float: right;
                ">
                    {media_html}
                    <pre style="
                        margin:0;
                        white-space:pre-wrap;
                        word-wrap:break-word;
                        font-family:'Segoe UI', sans-serif;
                        font-size:13px;
                        color:#222;
                    ">{record.body_text or ''}</pre>
                    {'<div style="color:#999;font-size:11px;margin-top:5px;">' + record.footer_text + '</div>' if record.footer_text else ''}
                     <div style="margin-top:10px;">{buttons_html}</div>
                </div>
            """

            whatsapp_html = f"""<div class="dtemplate_view_change" style="border:none;padding:0;background:transparent;border-radius:0;overflow:initial;max-width:340px;margin-left:auto;margin-right:auto;width:130%">
                <div class="dcard3" style="position:relative;box-shadow:2px 20px 43px rgba(0,0,0,.2);display:inline-block;border:5px solid #fff;border-radius:45px;padding:0;overflow:hidden;width:100%">
                    <div class="dhead_top_w1" style="height:70px;background:#075e55;"></div>
                    <div class="dcard2" style="border:none;border-radius:0;padding:15px;background:url('/whatsapp_api_odoo03/static/src/img/whatsapp_bg.png');height:460px;overflow-y:auto">
                        {chat_bubble}
                    </div>
                    <div class="dfooter_top_w1" style="height:75px;background:#f6f6f6;position:relative">
                    <div class="iicon2" style="position:absolute;background:url('/whatsapp_api_odoo03/static/src/img/mobile_bar.png');top:7px;width:310px;height:27px;left:0;right:0;margin:0 auto;background-size:100%"></div>
                    <div class="linnne" style="width:110px;height:5px;border-radius:10px;background:#212529;bottom:10px;position:absolute;left:0;right:0;margin:0 auto"></div>
                    </div>
                </div>
            </div>"""

            # --- White wrapper to avoid black background ---
            record.message_preview = Markup(f"""
                <div style="background:#fff;padding:25px;text-align:center;">
                    {whatsapp_html}
                </div>
            """)
    
class WhatsappTemplateVariable(models.Model):
    _name = 'whatsapp.template.variable'
    _description = 'WhatsApp Template Variable'
    _order = 'sequence'

    template_id = fields.Many2one(
        'whatsapp.template',
        ondelete='cascade'
    )
    sequence = fields.Integer()
    key = fields.Char(string="Variable", readonly=True)
    variable_type = fields.Selection([
        ('custom', 'Custom'),
        ('user_name', 'User Name'),
        ('current_date', 'Current Date'),
    ], default='custom')

    custom_value = fields.Char(string="Custom Value")

    @api.onchange('variable_type')
    def _onchange_variable_type(self):
        for rec in self:
            if rec.variable_type == 'user_name':
                rec.custom_value = 'name'
            elif rec.variable_type == 'current_date':
                rec.custom_value = 'date'
            else:
                rec.custom_value = ''

class WhatsappChatMessage(models.Model):
    
    _name = "whatsapp.chat.message" 
    _description = "WhatsApp Chat Message"

    partner_id = fields.Many2one("res.partner", required=True)
    message = fields.Text()
    is_from_user = fields.Boolean(default=False)
    date = fields.Datetime(default=fields.Datetime.now)

    attachment_name = fields.Char()
    attachment_data = fields.Binary()
    attachment_type = fields.Selection([
        ('image', 'Image'),
        ('video', 'Video'),
        ('doc', 'Document'),
        ('audio', 'Audio'),
    ])
    attachment_url = fields.Char(compute="_compute_attachment_url")
    read_msg = fields.Boolean(default=False)
    api_status = fields.Char(string="API Status", default="Pending")
    single_tick= fields.Boolean(default=True)
    double_tick= fields.Boolean(default=False)
    read_cust_message= fields.Boolean(default=False)

    @api.depends("attachment_data")
    def _compute_attachment_url(self):
        for rec in self:
            if rec.attachment_data:
                rec.attachment_url = f"/web/content/{rec.id}?model=whatsapp.chat.message&field=attachment_data"
            else:
                rec.attachment_url = False

    @api.model
    def send_chat_message(self, partner_id, message, attachment=False):
        """ Send WhatsApp message (text or media) and store it in Odoo. """

        check_subscription= self.env['whatsapp.payment.wizard'].check_subscription_expiration()
        if check_subscription == False:
             raise UserError("Your WhatsApp Connector monthly plan has expired.")
        
        partner = self.env['res.partner'].browse(partner_id)
        print("partner......",partner)
        if not partner:
            raise ValueError("Invalid partner ID")

        partner_phone = partner.mobile
        print("partner_phone......",partner_phone)
        if not partner_phone:
            raise ValueError("Partner does not have a phone number")

        # STEP 1: Create local chat record in Odoo
        vals = {
            "partner_id": partner.id,
            "message": message,
            "is_from_user": True,
            "date": fields.Datetime.now(),
        }
        print("vals......",vals)

        attachment_type = None
        if attachment:
            content_type = attachment.get("type", "")
            attachment_type = "doc"
            if "image" in content_type:
                attachment_type = "image"
            elif "video" in content_type:
                attachment_type = "video"
            elif "audio" in content_type:
                attachment_type = "audio"

            vals.update({
                "attachment_name": attachment["name"],
                "attachment_data": attachment["content"],
                "attachment_type": attachment_type,
            })

        chat_message = self.create(vals)

        setting_object = self.env["ir.config_parameter"].sudo()
        base_url = setting_object.get_param("go4whatsapp_url")
        org_id = setting_object.get_param("org_id")
        apikey = setting_object.get_param("apikey")
        secureKey = setting_object.get_param("secureKey")   

        try:
            # STEP 2A: If only text (no attachment)
            if not attachment:
                url = f"{base_url}/odooDeveloperApi/sendTextMessage/v1/{apikey}/{secureKey}"
                payload = json.dumps({
                    "customerMobileNo": partner_phone,
                    "message": message
                })
                headers = {'Content-Type': 'application/json'}
                response = requests.post(url, headers=headers, data=payload, timeout=15)
                print(" Text API Response:", response.text)

            # STEP 2B: If attachment present
            else:
                url = f"{base_url}/odooDeveloperApi/sendFileMessage/v1/{apikey}/{secureKey}"
                payload = {
                    'customerMobileNo': partner_phone,
                    'message': message,
                    'msgType': attachment_type
                }
                file_content = base64.b64decode(attachment['content'])
                files = [
                    ('file', (attachment['name'], file_content, attachment['type']))
                ]
                response = requests.post(url, data=payload, files=files, timeout=15)

            chat_message.sudo().write({"api_status": "Success"})
        except Exception as e:
            print(f" Error sending WhatsApp message: {e}")
            chat_message.sudo().write({"api_status": f"Failed: {e}"})

        return chat_message.id
    

    # ----------------------------------------------------------
    # New Function: Send Template Message
    # ----------------------------------------------------------
    @api.model
    def send_template_message(self, partner_id, template_id):
        """Send an approved WhatsApp template message."""

        check_subscription= self.env['whatsapp.payment.wizard'].check_subscription_expiration()
        if check_subscription == False:
             raise UserError("Your WhatsApp Connector monthly plan has expired.")
        

        partner = self.env["res.partner"].browse(partner_id)
        template_id = self.env["whatsapp.template"].search([("template_id", "=", template_id)], limit=1)

        print("..............",template_id)

        if template_id.header_type == "document":
            attachment_type="doc"
        else:
            attachment_type=template_id.header_type

        attachment_binary = False
        if template_id.header_image:
            try:
                response = requests.get(template_id.header_image)
                if response.status_code == 200:
                    attachment_binary = base64.b64encode(response.content)
                else:
                    print(" Failed to download image:", response.status_code)
            except Exception as e:
                print(" Error downloading image:", e)

        if not partner or not template_id:
            raise ValueError("Invalid partner or template")

        partner_phone = partner.mobile
        if not partner_phone:
            raise ValueError("Partner does not have a phone number")
        
        setting_object = self.env["ir.config_parameter"].sudo()
        base_url = setting_object.get_param("go4whatsapp_url")
        
        org_id = setting_object.get_param("org_id")
        #Create local record for history
        chat_message = self.create({
            "partner_id": partner.id,
            "message": template_id.body_text,
            "is_from_user": True,
            "date": fields.Datetime.now(),
            "attachment_name" : template_id.template_name,
            "attachment_type" : attachment_type,
            "attachment_data": attachment_binary

        })

        try:
            url = f"{base_url}/sendTemplatedToTicket"
            payload = json.dumps({
            "orgId": org_id,
            "ticketId": partner.ticketId,
            "customerId": partner.customerId,
            "userId": partner.userId,
            "msgType": "",
            "templateIds": [
                {
                "templatedId": template_id.template_id
                }
            ]
            })
            headers = {
            'Content-Type': 'application/json'
            }

            response = requests.request("POST", url, headers=headers, data=payload)

        except Exception as e:
            print(f" Error sending WhatsApp template: {e}")
            # chat_message.sudo().write({"api_status": f"Failed: {e}"})
        # return chat_message.id
        return True
    
class WhatsappVariableWizard(models.TransientModel):
    _name = 'whatsapp.variable.wizard'
    _description = 'WhatsApp Variable Wizard'

    variable = fields.Selection([
        ('user_name', 'User Name'),
        ('order_no', 'Order Number'),
        ('amount', 'Total Amount'),
        ('current_date', 'Current Date'),
    ], required=True)

class WhatsappAddVariableWizard(models.TransientModel):
    _name = 'whatsapp.add.variable.wizard'

    template_id = fields.Many2one('whatsapp.template', required=True)
    variable_type = fields.Selection([
        ('custom', 'Custom'),
        ('user_name', 'User Name'),
        ('current_date', 'Current Date'),
    ], default='custom')    

class WhatsappTemplateButton(models.Model):
    _name = 'whatsapp.template.button'
    _description = 'WhatsApp Template Button'

    # THIS FIELD WAS MISSING OR WRONG
    template_id = fields.Many2one(
        'whatsapp.template',
        string='Template',
        ondelete='cascade',
        required=True
    )

    action_type = fields.Selection([
        ('contact', 'Contact'),
        ('visit_website', 'Visit Website'),
    ], default='contact', required=True)

    button_text = fields.Char(string="Button Text")

    # Contact
    phone_number = fields.Char(string="Mobile Number")

    # Website
    url_type = fields.Selection([
        ('static', 'Static'),
        ('dynamic', 'Dynamic'),
    ], default='static')

    website_url = fields.Char(string="Website URL")


class IrConfigParameter(models.Model):
    _inherit = 'ir.config_parameter'

    @api.model
    def get_multi_params(self, keys):  
        """
        keys: list of strings 
        return: dict
        """
        ICP = self.sudo()
        result = {}
        for key in keys:
            result[key] = ICP.get_param(key)
        return result
    

    @api.model
    def SendVerifiedemail(self):
        ICP = self.env["ir.config_parameter"].sudo()

        host_url = ICP.get_param("go4whatsapp_url")
        org_id = ICP.get_param("org_id")
        apikey = ICP.get_param("apikey")
        secureKey = ICP.get_param("secureKey")

        url = f"{host_url}/odooDeveloperApi/odooSendMailOnGreenTick/v1/{apikey}/{secureKey}"

        payload = {
            "orgId": org_id
        }

        headers = {
            'Content-Type': 'application/json'
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=20
            )

            response_data = response.json()
            print("response....", response_data)

            # Optional: set config based on response
            if response_data.get("ErrorCode") == 200:
                ICP.set_param('whatsapp.green_tick', "pending")

            # ✅ RETURN ACTUAL RESPONSE
            return response_data

        except Exception as e:
            return {
                "ErrorCode": 500,
                "ErrorMessage": str(e)
            }
        

class WhatsappSubscriptionExpiredWizard(models.TransientModel):
    _name = 'whatsapp.subscription.expired.wizard'
    _description = 'WhatsApp Subscription Expired'

    def action_subscribe_now(self):

        ICP = self.env["ir.config_parameter"].sudo()
        payment_link = ICP.get_param("payment_link")

        return {
                'type': 'ir.actions.act_window',
                'name': 'Confirm Your Payment',
                'res_model': 'payment.confirm.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'payment_url': payment_link,
                    'default_apply_free_trial_plan': False,
                }
            }