from odoo import api, fields, models, _
from odoo.exceptions import UserError
import requests
import json
import uuid
from datetime import timedelta
import random
class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    go4whatsapp_url = fields.Char(string="Go4Whatsapp URL")
    template_id = fields.Char(string="Template ID")
    org_id = fields.Char(string="Organization ID")
    Subscription_expire_date = fields.Date(
        string='Subscription Expire Date' ,readonly=True
    )

    shippingTemplatedId = fields.Char(string="Shipping Template ID")
    apikey = fields.Char(string="API Key")
    secureKey = fields.Char(string="Secure Key")

    odoo_expire_date = fields.Date(
        string='Odoo Expire Date', readonly=True
    )

    go4whatsapp_access_token= fields.Char(string="Go4whatsapp access token")

    install_popup_shown = fields.Boolean(default=False)

    user_generated_id = fields.Char(
        string="User Generated ID",
        readonly=True,
        compute="_compute_user_generated_id"
    )
    user_email= fields.Char(string=" Email address")
    user_mobile_no= fields.Char(string="Mobile Number")
    user_name= fields.Char(string="Name")
    is_api_active = fields.Boolean(
        string="API Active",
        config_parameter='whatsapp.is_api_active'
    )
    
      

    def action_refresh_api_status(self):
        self.ensure_one()

        setting_object = self.env["ir.config_parameter"].sudo()
        host_url= setting_object.get_param("go4whatsapp_url")
        apikey= setting_object.get_param("apikey")
        secureKey= setting_object.get_param("secureKey")  


        url = f"{host_url}/developerApi/developerApiGetMetaStatus/v1/{apikey}/{secureKey}"

        payload = {}
        headers = {
        'Cookie': 'HttpOnly'
        }

        response = requests.request("GET", url, headers=headers, data=payload)
        response_json = response.json()
        print(".............",response_json)

        if response_json["ErrorCode"] == 200 and response_json["status"] == "APPROVED":
            ICP = self.env['ir.config_parameter'].sudo()
            ICP.set_param('whatsapp.is_api_active', True)
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }

    def _compute_user_generated_id(self):
        param = self.env['ir.config_parameter'].sudo()
        for rec in self:
            rec.user_generated_id = param.get_param('whatsapp_api_odoo03.user_generated_id', default='')

        

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        get_param = self.env['ir.config_parameter'].sudo().get_param
        res['go4whatsapp_url'] = get_param('go4whatsapp_url')
        res['template_id'] = get_param('template_id')
        res['org_id'] = get_param('org_id')

        res['shippingTemplatedId'] = get_param('shippingTemplatedId')
        res['apikey'] = get_param('apikey')
        res['secureKey'] = get_param('secureKey')

        res['Subscription_expire_date'] = get_param('Subscription_expire_date')
        res['odoo_expire_date'] = get_param('odoo_expire_date')
        res['go4whatsapp_access_token']=get_param('go4whatsapp_access_token')
        res['user_generated_id'] = get_param('user_generated_id')

        res['user_email'] = get_param('user_email')
        res['user_mobile_no']=get_param('user_mobile_no')
        res['user_name'] = get_param('user_name')
        res['is_api_active'] = (
          get_param('whatsapp.is_api_active') == 'True'
                )
        return res

    @api.model
    def set_values(self):
        set_param = self.env['ir.config_parameter'].sudo().set_param
        set_param('go4whatsapp_url',
                  self.go4whatsapp_url)
        set_param('template_id',
                  self.template_id)
        set_param('org_id',
                  self.org_id)
        set_param('Subscription_expire_date',self.Subscription_expire_date)
        set_param('odoo_expire_date',self.odoo_expire_date)
        set_param('shippingTemplatedId',
                  self.shippingTemplatedId)
        set_param('apikey',
                  self.apikey)               
        set_param('secureKey', 
                  self.secureKey)
        set_param('go4whatsapp_access_token', 
                  self.go4whatsapp_access_token)
        set_param('user_generated_id', 
                  self.user_generated_id)
        
        set_param('user_email', 
                  self.user_email)
        set_param('user_mobile_no', 
                  self.user_mobile_no)
        set_param('user_name', 
                  self.user_name) 
        set_param('is_api_active', 
                  self.is_api_active) 
        
        super(ResConfigSettings, self).set_values()

    def action_open_payment_renew(self):

        setting_object = self.env["ir.config_parameter"].sudo()
        host_url= setting_object.get_param("go4whatsapp_url")
        org_id = setting_object.get_param("org_id")

        url = f"{host_url}/odoo/getOdooSubscriptionPaymentLink"

        payload = {}
        headers = {
        'Cookie': 'HttpOnly'
        }

        response = requests.request("GET", url, headers=headers, data=payload)
        response_json = response.json()
        if response_json["ErrorCode"] == 200 :

            Price = response_json["OdooPlan"]["packageId"]["price"]

            
            self.env['whatsapp.payment.wizard'].create({
                'amount': Price,  
                'payment_link_id': response_json["OdooPlan"]["paymentLink"],
                'user_id': org_id,
                'status': 'not_done',
                'payment_status':'pending',
            })

            return {
                "type": "ir.actions.act_url",
                "url": response_json["OdooPlan"]["paymentLink"],
                "target": "new",
            }
        
           #odoo_plan = response_json.get("OdooPlan")
  
 

    def action_open_payment_cancel_subscription(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Cancel Whatsapp Subscription',
            'res_model': 'cancel.subscription.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('whatsapp_api_odoo03.view_cancel_subscription_wizard').id,
            'target': 'new',
        }
    
    def enbeded_signup(self):

        setting_object = self.env["ir.config_parameter"].sudo()
        host_url= setting_object.get_param("go4whatsapp_url")
        apikey= setting_object.get_param("apikey")
        secureKey= setting_object.get_param("secureKey")  
        web_link= setting_object.get_param("web.base.url")  


        return {
            'type': 'ir.actions.act_url',
            'url': f'{host_url}/developerApi/embededSignup/v1/{apikey}/{secureKey}?websiteurl={web_link}',
            'target': 'new',  # opens in popup/modal
        }

class CancelSubscriptionWizard(models.TransientModel):
    _name = "cancel.subscription.wizard"
    _description = "Cancel Subscription Confirmation"

    def action_confirm_cancel(self):
        import requests
        import json

        setting_object = self.env["ir.config_parameter"].sudo()
        host_url= setting_object.get_param("go4whatsapp_url")
        org_id = setting_object.get_param("org_id")

        Wizard = self.env["whatsapp.payment.wizard"]
        last_entry = Wizard.search([], order="id desc", limit=1)
        print("last_entry....",last_entry,last_entry.status)
        # Condition
        subscription_id = last_entry.subscription_id


        url = f"{host_url}/odoo/unsubscribePlan"

        payload = json.dumps({
        "subscriptionID": subscription_id,
        "orgId": org_id,
        "reason": "not define"
        })
        headers = {
        'Content-Type': 'application/json',
        'Cookie': 'HttpOnly'
        }

        response = requests.request("POST", url, headers=headers, data=payload)
        try:
            response_json = response.json()
        except Exception:
            raise UserError("Invalid API Response")
        

        # Step 1 — Check success
        if response_json.get("ErrorCode") == 200:
            cancel_data = response_json.get("cancelPaymentSubsciption", {})

            # Step 2 — Check if cancel was successful
            if cancel_data.get("iscancel") == 1:
                
                print("Subscription successfully cancelled")
                
                last_entry.status="cancel"

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Success',
                        'message': 'Your subscription has been successfully cancelled.',
                        'type': 'success',
                        'sticky': False,
                        'next': {
                            'type': 'ir.actions.client',
                            'tag': 'reload',
                        }
                    }
                }

            else:
                raise UserError("Failed to cancel subscription. Please try again.")
        else:
            msg = response_json.get("ErrorMessage", "Unknown Error")
            raise UserError(f"API Error: {msg}")


class PaymentConfirmWizard(models.TransientModel):
    _name = 'payment.confirm.wizard'
    _description = 'Confirm Payment'

    apply_free_trial_plan = fields.Boolean(default=False)

    def action_open_payment(self):
        payment_url = self.env.context.get('payment_url')

        return {
            'type': 'ir.actions.act_url',
            'url': payment_url,
            'target': 'new'
        }
    
    def assign_free_trial_plan(self):
        print("assign 7 day free trial plan.")

        setting = self.env['ir.config_parameter'].sudo()
        base_url = setting.get_param("go4whatsapp_url")
        org_id = setting.get_param("org_id")  
        Apistatus = setting.get_param("whatsapp.is_api_active")     

        url = f"{base_url}/extensions/assignFreePlan"

        payload = json.dumps({
        "orgId": org_id,
        "platform": "Odoo"
        })

        headers = {
        'Content-Type': 'application/json',
        'Cookie': 'HttpOnly; HttpOnly'
        }

        response = requests.request("POST", url, headers=headers, data=payload)

        response_json = response.json()
        if response_json.get('ErrorCode') != 200:
            errormessage= response_json.get('ErrorMessage')
            raise UserError(errormessage)
        

        from datetime import datetime, timedelta

        subscription_date = datetime.utcnow()
        expiry_date = subscription_date + timedelta(days=7)

        # agar string format chahiye (same as tum use kar rahe ho)
        subscription_date = subscription_date.strftime("%Y-%m-%d %H:%M:%S")
        expiry_date = expiry_date.strftime("%Y-%m-%d %H:%M:%S")

        # Update / Create wizard record
        Wizard = self.env["whatsapp.payment.wizard"]

        last_entry = Wizard.search([], order="id desc", limit=1)
        if last_entry:
            Wizard.search([('id', '!=', last_entry.id)]).write({'status': 'expired'})

        vals = {
            'amount': 0,
            'status': 'done',
            'payment_status': 'success',
            'start_datetime': subscription_date,
            'end_datetime': expiry_date,
            'subscription_id': "Trail",
        }

        if last_entry and last_entry.payment_status == 'pending':
            last_entry.write(vals)
        else:
            Wizard.create(vals)

        menuitem = self.env["ir.ui.menu"].search([
                        ('name', '=', 'Go4whatsapp Connector'),
                    ])
        if menuitem:
            menuitem.write({"action": False})
        Apistatus=False
        if Apistatus == True:
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',   
            }

        return {
            "name": "Help Information",
            "type": "ir.actions.act_window",
            "res_model": "help.wizard",
            "view_mode": "form",
            "view_id": self.env.ref("whatsapp_api_odoo03.view_help_wizard_form").id,
            "target": "new",
        }

    def action_i_have_paid(self):
        import requests
        import json

        setting = self.env['ir.config_parameter'].sudo()
        base_url = setting.get_param("go4whatsapp_url")
        org_id = setting.get_param("org_id")  
        Apistatus = setting.get_param("whatsapp.is_api_active")     
        odooApiUrl = setting.get_param("web.base.url")

        url = f"{base_url}/odoo/getOdooSubscription"

        payload = json.dumps({
        "orgId": org_id,
        "odooExtensionApiUrl": f"{odooApiUrl}/"

        })
        print("payload...",payload)

        headers = {
        'Content-Type': 'application/json',
        'Cookie': 'HttpOnly'
        }

        response = requests.request("POST", url, headers=headers, data=payload)

        response_json = response.json()
        if response_json.get('ErrorCode') != 200:
            # errormessage= response_json.get('ErrorMessage')
            # raise UserError(errormessage)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Payment Pending',
                    'message': 'Payment was not completed yet. Please pay first.',
                    'type': 'danger',
                    'sticky': True,
                }
            }

        
        # Subscription data
        odoo_pkg = response_json.get('getOdooSubscription')
        if not odoo_pkg:
            raise UserError("Please pay first to activate subscription.")

        #  Cancel check 
        if odoo_pkg.get('iscancel') == 1:
            raise UserError("Your subscription has been cancelled. Please renew.")
        
        expiry_date = self.convert_iso_date(odoo_pkg.get("expiryDate"))
        subscription_date = self.convert_iso_date(odoo_pkg.get("subscriptionDate"))

        # Update / Create wizard record
        Wizard = self.env["whatsapp.payment.wizard"]

        last_entry = Wizard.search([], order="id desc", limit=1)
        if last_entry:
            Wizard.search([('id', '!=', last_entry.id)]).write({'status': 'expired'})

        vals = {
            'amount': odoo_pkg.get("price", 0),
            'status': 'done',
            'payment_status': 'success',
            'start_datetime': subscription_date,
            'end_datetime': expiry_date,
            'subscription_id': odoo_pkg.get("subscriptionID"),
        }

        if last_entry and last_entry.payment_status == 'pending':
            last_entry.write(vals)
        else:
            Wizard.create(vals)

        menuitem = self.env["ir.ui.menu"].search([
                        ('name', '=', 'Go4whatsapp Connector'),
                    ])
        if menuitem:
            menuitem.write({"action": False})

        if Apistatus == True:
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',   
            }

        return {
            "name": "Help Information",
            "type": "ir.actions.act_window",
            "res_model": "help.wizard",
            "view_mode": "form",
            "view_id": self.env.ref("whatsapp_api_odoo03.view_help_wizard_form").id,
            "target": "new",
        }
    

    def convert_iso_date(self,date_str):
        if not date_str:
            return None
        # Example: 2026-01-03T09:44:01.000Z → 2026-01-03 09:44:01
        clean = date_str.replace("T", " ").replace("Z", "")
        if "." in clean:  # remove milliseconds
            clean = clean.split(".")[0]
        return clean      

class OtpValidate(models.TransientModel):
    _name = 'otp.validate'
    _description = 'OTP Validation'

    mobile_number = fields.Char(string="Mobile Number", readonly=True)
    generated_otp = fields.Char(string="Generated OTP", readonly=True)
    entered_otp = fields.Char(string="Enter OTP")
    email = fields.Char(string="email")
    
    
    def action_verify_otp(self):

        self.env['ir.config_parameter'].sudo().set_param('org_id','')
        self.env['ir.config_parameter'].sudo().set_param('apikey','')
        self.env['ir.config_parameter'].sudo().set_param('secureKey','')  
        self.env['ir.config_parameter'].sudo().set_param('user_mobile_no','')  
        self.env['ir.config_parameter'].sudo().set_param('user_email','')  
        self.env['ir.config_parameter'].sudo().set_param('whatsapp.is_api_active',False) 
        self.env['ir.config_parameter'].sudo().set_param('whatsapp.green_tick',"notverify") 

        self.ensure_one()
        
        if not self.entered_otp:
            raise UserError("Please enter your otp.")
        
        setting = self.env['ir.config_parameter'].sudo()
        base_url = setting.get_param("go4whatsapp_url")  
        odooApiUrl = setting.get_param("web.base.url")
        url = f"{base_url}/odoo/checkBusinessNo"

        payload = json.dumps({
        "businesNumber": self.mobile_number,
        "platform": "odoo",
        "otp": self.entered_otp,
        "odooExtensionApiUrl": f"{odooApiUrl}/"
        })
        print("payload.......",payload)
        headers = {
        'Content-Type': 'application/json',
        'Cookie': 'HttpOnly'
        }

        response = requests.request("POST", url, headers=headers, data=payload)
        response_json = response.json()
        if response_json.get('ErrorCode') != 200:
            errormessage= response_json.get('ErrorMessage')
            raise UserError(errormessage)
        

        self.env['ir.config_parameter'].sudo().set_param('org_id',response_json.get("orgData", {}).get("_id"))  

        self.env['ir.config_parameter'].sudo().set_param('user_name',response_json.get("orgData", {}).get("businessName"))  
        self.env['ir.config_parameter'].sudo().set_param('user_mobile_no',response_json.get("orgData", {}).get("businessNumber"))  
        self.env['ir.config_parameter'].sudo().set_param('user_email',response_json.get("orgData", {}).get("email"))  

        Apistatus= response_json.get("orgData", {}).get("metaStatusEnum")
        print("Apistatus....",Apistatus)
        if Apistatus == "APPROVED":
            self.env['ir.config_parameter'].sudo().set_param('whatsapp.is_api_active',True)
        else:
            self.env['ir.config_parameter'].sudo().set_param('whatsapp.is_api_active',False) 
            self.env['ir.config_parameter'].sudo().set_param('whatsapp.green_tick',"notverify")   
        self.env['ir.config_parameter'].sudo().set_param('apikey',response_json["apikey"])
        self.env['ir.config_parameter'].sudo().set_param('secureKey',response_json["secureKey"])  
        self.env['ir.config_parameter'].sudo().set_param('whatsapp_api_odoo03.whatsapp_api_odoo03_flow',True)

        odoo_pkg = response_json.get("extensionsAssignPackage")
        applyFreeTrailPlan = response_json["applyFreeTrailPlan"]
        print("applyFreeTrailPlan.......",applyFreeTrailPlan,type(applyFreeTrailPlan))
        odoo_plan = response_json.get("extensionsPlan")
        package = odoo_plan.get("packageId")
        is_valid_package = False
        
        if odoo_pkg:

            if odoo_pkg["iscancel"] != 1:
                is_valid_package = True
        else:
            is_valid_package = False

        if is_valid_package == False:
            #Get paymentLink from OdooPlan
            payment_link = None
            if odoo_plan and odoo_plan.get("paymentLink"):
                payment_link = odoo_plan.get("paymentLink")
                self.env['ir.config_parameter'].sudo().set_param('payment_link',payment_link)  

            self.env['whatsapp.payment.wizard'].create({
                'amount': package.get("price"),  
                'payment_link_id': payment_link,
                'user_id': response_json.get("orgData", {}).get("_id"),
                'status': 'not_done',
                'payment_status':'pending',
            })

            return {
                    'type': 'ir.actions.act_window',
                    'name': 'Confirm Your Payment',
                    'res_model': 'payment.confirm.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'payment_url': payment_link,
                        'default_apply_free_trial_plan': applyFreeTrailPlan,
                    }
                }
        else:
            
            import pytz
            from odoo import fields

            # Clean & convert raw dates
            expiry_date_str = self.convert_iso_date(odoo_pkg.get("expiryDate"))
            subscription_date_str = self.convert_iso_date(odoo_pkg.get("subscriptionDate"))

            expiry_date_utc = fields.Datetime.from_string(expiry_date_str)
            subscription_date_utc = fields.Datetime.from_string(subscription_date_str)

            # REMOVE timezone conversion → Odoo does it automatically
            expiry_date_naive = expiry_date_utc.replace(tzinfo=None)
            subscription_date_naive = subscription_date_utc.replace(tzinfo=None)

            self.env['whatsapp.payment.wizard'].create({
            'amount': package.get("price"),  
            'payment_link_id': odoo_plan.get("paymentLink"),
            'user_id': response_json.get("orgData", {}).get("_id"),
            'status': 'done',
            'payment_status':'success',
            "start_datetime":subscription_date_naive,
            "end_datetime" : expiry_date_naive,
            "subscription_id": odoo_pkg["subscriptionID"]
            })

            menuitem = self.env["ir.ui.menu"].search([
                        ('name', '=', 'Go4whatsapp Connector'),
                        
                    ])
            if menuitem:
                menuitem.write({"action": False})
            (".........................",Apistatus)
            if Apistatus == "APPROVED":
                return {
                    'type': 'ir.actions.client',
                    'tag': 'reload',   
                }

            return {
                "name": "Help Information",
                "type": "ir.actions.act_window",
                "res_model": "help.wizard",
                "view_mode": "form",
                "view_id": self.env.ref("whatsapp_api_odoo03.view_help_wizard_form").id,
                "target": "new",
            }

    def convert_iso_date(self,date_str):
        if not date_str:
            return None
        # Example: 2026-01-03T09:44:01.000Z → 2026-01-03 09:44:01
        clean = date_str.replace("T", " ").replace("Z", "")
        if "." in clean:  # remove milliseconds
            clean = clean.split(".")[0]
        return clean             
                   
class InstallationPopup(models.TransientModel):
    
    _name = "installation.popup"
    _description = "Installation Popup"

    user_generated_id = fields.Char(
        string="User ID",
        readonly=True
    )
    user_email= fields.Char(string=" Email address")
    user_mobile_no= fields.Char(string="Mobile Number")
    user_name= fields.Char(string="Name")

    country_id = fields.Many2one(
        "res.country",
        string="Country",
        required=True
    )

    # This field will auto-store the country code
    country_code = fields.Char(
        string="Country Code",
        compute="_compute_country_code",
        store=True
    )


    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        res['is_mobile_verified'] = 'false'
        return res

    @api.depends("country_id")
    def _compute_country_code(self):
        for rec in self:
            if rec.country_id and rec.country_id.phone_code:
                rec.country_code = f"+{rec.country_id.phone_code}"
            else:
                rec.country_code = ""

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)

        param = self.env['ir.config_parameter'].sudo()
        saved_id = param.get_param('whatsapp_api_odoo03.user_generated_id')

        if not saved_id:
            saved_id = str(uuid.uuid4())[:8]
            param.set_param('whatsapp_api_odoo03.user_generated_id', saved_id)

        res['user_generated_id'] = saved_id
        return res
    
    def action_check_mobileisvalid(self):
        self.ensure_one()
        try: 
            full_mobile = f"{self.country_code}{self.user_mobile_no}"
            if not self.user_mobile_no:
                raise UserError("Please enter your Business number.")

            otp = random.randint(100000, 999999)

            
            setting = self.env['ir.config_parameter'].sudo()
            base_url = setting.get_param("go4whatsapp_url")

            url = f"{base_url}/extensions/signUp"

            payload = json.dumps({
            "mobileNo": full_mobile,
            "isDesktopApplication": False
            })
            headers = {
            'Content-Type': 'application/json',
            'Cookie': 'HttpOnly'
            }
            response = requests.request("POST", url, headers=headers, data=payload)
            print(response.text)
            result = response.json()

            email = result.get('SignInUser', {}).get('email')


            # Open same saved record in popup
            if result.get('ErrorCode') == 200:

                otp_record = self.env['otp.validate'].create({
                    'mobile_number': full_mobile,
                    'generated_otp': otp,
                    'email':email
                })

                return {
                    'type': 'ir.actions.act_window',
                    'name': 'OTP Verification',
                    'res_model': 'otp.validate',
                    'view_mode': 'form',
                    'res_id': otp_record.id,   
                    'view_id': self.env.ref(
                        'whatsapp_api_odoo03.otp_validate_form_view'
                    ).id,
                    'target': 'new',
                }
            
            else:
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Registration Form',
                    'res_model': 'installation.popup',
                    'view_mode': 'form',
                    'view_id': self.env.ref(
                        'whatsapp_api_odoo03.registration_popup_form'
                    ).id,
                    'target': 'new',
                    'context': {
                        'default_user_mobile_no': self.user_mobile_no,
                        'default_country_code': self.country_code,
                        'default_country_id': self.country_id.id,
                    }
                }
        except Exception as e :
            raise UserError(e)

    def action_submit_popup(self):
      
      try: 

        server_tz = self.env.user.tz
        full_mobile = f"{self.country_code}{self.user_mobile_no}"

        self.env['ir.config_parameter'].sudo().set_param('system_timezone', server_tz)
        self.env['ir.config_parameter'].sudo().set_param('user_email',self.user_email)  
        self.env['ir.config_parameter'].sudo().set_param('user_mobile_no',full_mobile)
        self.env['ir.config_parameter'].sudo().set_param('user_name',self.user_name)

        setting_object = self.env["ir.config_parameter"].sudo()
        host_url= setting_object.get_param("go4whatsapp_url")

        url = f"{host_url}/odooRegistration/CreateOdooFreePacakgeuser"

        payload = json.dumps({

        "isOdooRegistration": "true",
        "businessname": self.user_name,
        "businesNumber": full_mobile,
        "email": self.user_email,
        "userTimeZone": server_tz
        })
        print("payload.........10",payload,url)
        headers = {
        'Content-Type': 'application/json',
        'Cookie': 'HttpOnly'
        }

        response = requests.request("POST", url, headers=headers, data=payload)
        response_json = response.json()
        print(".............response_json",response_json)

        if response_json["ErrorCode"] == 200 :
           
           self.env['ir.config_parameter'].sudo().set_param('org_id',response_json.get("orgData", {}).get("_id"))
           self.env['ir.config_parameter'].sudo().set_param('apikey',response_json["apikey"])
           self.env['ir.config_parameter'].sudo().set_param('secureKey',response_json["secureKey"])  
           self.env['ir.config_parameter'].sudo().set_param('whatsapp_api_odoo03.whatsapp_api_odoo03_flow',True)

           Apistatus= response_json.get("orgData", {}).get("metaStatusEnum")
           print("Apistatus....",Apistatus)
           if Apistatus == "APPROVED":
                self.env['ir.config_parameter'].sudo().set_param('whatsapp.is_api_active',True)
           else:
                self.env['ir.config_parameter'].sudo().set_param('whatsapp.is_api_active',False) 
                self.env['ir.config_parameter'].sudo().set_param('whatsapp.green_tick',"notverify") 

           odoo_pkg = response_json.get("odooAssignPackage")
           odoo_plan = response_json.get("OdooPlan")
           package = odoo_plan.get("packageId")
           is_valid_package = False
           if odoo_pkg:

                if odoo_pkg["iscancel"] != 1:
                    is_valid_package = True
           else:
                is_valid_package = False

           if is_valid_package == False:
                #Get paymentLink from OdooPlan
                payment_link = None
                if odoo_plan and odoo_plan.get("paymentLink"):
                    payment_link = odoo_plan.get("paymentLink")
                    self.env['ir.config_parameter'].sudo().set_param('payment_link',payment_link) 

                self.env['whatsapp.payment.wizard'].create({
                    'amount': package.get("price"),  
                    'payment_link_id': payment_link,
                    'user_id': response_json.get("orgData", {}).get("_id"),
                    'status': 'not_done',
                    'payment_status':'pending',
                })
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Confirm Your Payment',
                    'res_model': 'payment.confirm.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'payment_url': payment_link,
                        'default_apply_free_trial_plan': True,
                    }
                }
           
           else:
                
                import pytz
                from odoo import fields

                # Clean & convert raw dates
                expiry_date_str = self.convert_iso_date(odoo_pkg.get("expiryDate"))
                subscription_date_str = self.convert_iso_date(odoo_pkg.get("subscriptionDate"))

                expiry_date_utc = fields.Datetime.from_string(expiry_date_str)
                subscription_date_utc = fields.Datetime.from_string(subscription_date_str)

                # REMOVE timezone conversion → Odoo does it automatically
                expiry_date_naive = expiry_date_utc.replace(tzinfo=None)
                subscription_date_naive = subscription_date_utc.replace(tzinfo=None)

                Wizard = self.env["whatsapp.payment.wizard"]

                last_entry = Wizard.search([], order="id desc", limit=1)
                other_entries = Wizard.search([('id', '!=', last_entry.id)])
                other_entries.write({'status': 'expired'})

                if last_entry and last_entry.payment_status == 'pending':
                    last_entry.status = "done"
                    last_entry.payment_status = "success"
                    last_entry.start_datetime = subscription_date_naive
                    last_entry.end_datetime = expiry_date_naive
                    last_entry.subscription_id= odoo_pkg["subscriptionID"]

                else:
                    self.env['whatsapp.payment.wizard'].create({
                    'amount': package.get("price"),  
                    'payment_link_id': odoo_plan.get("paymentLink"),
                    'user_id': response_json.get("orgData", {}).get("_id"),
                    'status': 'done',
                    'payment_status':'success',
                    "start_datetime":subscription_date_naive,
                    "end_datetime" : expiry_date_naive,
                    "subscription_id": odoo_pkg["subscriptionID"]
                    })

                menuitem = self.env["ir.ui.menu"].search([
                            ('name', '=', 'Go4whatsapp Connector'),
                           
                        ])
                if menuitem:
                    menuitem.write({"action": False})  

                return {
                    "name": "Help Information",
                    "type": "ir.actions.act_window",
                    "res_model": "help.wizard",
                    "view_mode": "form",
                    "view_id": self.env.ref("whatsapp_api_odoo03.view_help_wizard_form").id,
                    "target": "new",
                }
        else:
            print(response_json)
            raise UserError(response_json["ErrorMessage"])

      except Exception as e:
        print(".........e", e)

        # If it's already UserError → frontend me show hoga
        if isinstance(e, UserError):
            raise e  

        # Otherwise convert into UserError so frontend can show it
        raise UserError(str(e))
            
    def convert_iso_date(self,date_str):
        if not date_str:
            return None
        # Example: 2026-01-03T09:44:01.000Z → 2026-01-03 09:44:01
        clean = date_str.replace("T", " ").replace("Z", "")
        if "." in clean:  # remove milliseconds
            clean = clean.split(".")[0]
        return clean             
               
    def check_subscription_expiration(self):
        from odoo.fields import Datetime
        last_plan = self.search(
            [],
            order='end_datetime desc',
            limit=1
        )

        # If no subscription found
        if not last_plan or not last_plan.end_datetime:
            return False

        # Current datetime (Odoo-safe)
        now = Datetime.now()

        # Compare end date with current date
        if last_plan.end_datetime < now:
            # Subscription expired
            return False

        # Subscription still active
        return True


class HelpWizard(models.TransientModel):
    _name = "help.wizard"
    _description = "Help & Contact Info Wizard"

    dummy = fields.Char()

    def action_close_refresh(self):

        menuitem = self.env["ir.ui.menu"].search([
                            ('name', '=', 'Go4whatsapp Connector')
                        ])
        
        if menuitem:
            menuitem.write({"action": True}) 


        return {
            'type': 'ir.actions.client',
            'tag': 'reload',   
        }
    
    def enbeded_signup(self):

        setting_object = self.env["ir.config_parameter"].sudo()
        host_url= setting_object.get_param("go4whatsapp_url")
        apikey= setting_object.get_param("apikey")
        secureKey= setting_object.get_param("secureKey")  
        web_link= setting_object.get_param("web.base.url")  


        return {
            'type': 'ir.actions.act_url',
            'url': f'{host_url}/developerApi/embededSignup/v1/{apikey}/{secureKey}?websiteurl={web_link}',
            'target': 'self',  # opens in popup/modal
        }
        
class WhatsappPaymentWizard(models.Model):
    _name = 'whatsapp.payment.wizard'
    _description = 'Whatsapp Payment Wizard'

    amount = fields.Char(string="Amount", readonly=True)
    payment_link_id = fields.Char(string="Payment Link ID", readonly=True)
    user_id = fields.Char(string="External ID", readonly=True)

    status = fields.Selection([
        ('expired', 'Expired'),
        ('not_done', 'Not Done'),
        ('done', 'Done'),
        ('cancel','Cancel'),
    ], string="Status", default='not_done')

    payment_status = fields.Selection([
        ('success', 'Success'),
        ('pending', 'Pending'),
    ], string="Payment Status", default='pending')

    start_datetime = fields.Datetime(string="Start Date & Time")
    end_datetime = fields.Datetime(string="End Date & Time")
    subscription_id= fields.Char(string="Subscription Id", readonly=True)

    def check_subscription_expiration(self):
        from odoo.fields import Datetime
        # Get last subscription (latest by end_datetime or create_date)
        last_plan = self.search(
            [],
            order='end_datetime desc',
            limit=1
        )

        # If no subscription found
        if not last_plan or not last_plan.end_datetime:
            return False

        # Current datetime (Odoo-safe)
        now = Datetime.now()

        # Compare end date with current date
        if last_plan.end_datetime < now:
            # Subscription expired
            return False

        # Subscription still active
        return True

