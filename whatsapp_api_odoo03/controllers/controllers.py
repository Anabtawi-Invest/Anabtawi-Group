from odoo import http,fields
from odoo.http import request
import json
import requests
import base64
from odoo.exceptions import UserError
from odoo.http import Controller, request, Response    
from datetime import date,datetime


class UserLoginController(http.Controller):

    @http.route('/CreateSalesOrder', type='http', auth='public', methods=['GET'], csrf=False)
    def create_sales_order(self, **kwargs):

        today_str = date.today().strftime("%Y-%m-%d")
        print("today_str....",today_str)
        url = kwargs.get('url')
        try: 

            setting_object = request.env["ir.config_parameter"].sudo()
            org_id = setting_object.get_param("org_id")
            print("org_id........", org_id)
            url = f"{url}/getAllCatalogOrdersByorgId"
            payload = json.dumps({
                "id": org_id,
                "limit": 1,
                "skip": 0,
                "startDate": today_str,
                "endDate": today_str,
                "search": ""
                })
            headers = {
            'Content-Type': 'application/json',
            'Cookie': 'HttpOnly'
            }
            response = requests.request("POST", url, headers=headers, data=payload)

            if response.status_code == 200:
                response_json = response.json()  # Parse the response to a dictionary
                # check data in catelog order by org id.
                GetAllOrderData = response_json.get("getAllCatalogOrdersByorgId", [])
                if GetAllOrderData: # Process the retrieved order data
                    for orderdata in GetAllOrderData:
                        saleid = request.env['sale.order'].sudo().search([
                                    ('whatsapp_sale_order_id', '=', orderdata["_id"])
                                ], limit=1)
                        print("order id ....",orderdata["_id"])
                        product_language = orderdata.get("orderLanguage","en")
                        if not saleid:
                            ProductList=[]
                            for item in orderdata["catalogorderitemsDetail"]:
                                
                                if item:
                                    item_detail = item.get("itemsDetail", {})
                                    sku_product_id = item_detail.get("sku")
                                    print("sku_product_id.....",sku_product_id)

                                    if not  sku_product_id:
                                        continue

                                    item_price = float(item.get("itemPrice", 0))
                                    total_price = float(item.get("totalItemPrice", 0))
                                    quantity = int(item.get("quantity", 1))
                                    
                                    item_name = item_detail.get("name", "Unnamed Product")
                                    whatsapp_product_id = item_detail.get("productId")

                                    # Check if the product already exists   
                                    product = request.env['product.template'].sudo().search([
                                        ('Product_sku_id', '=', sku_product_id)   
                                    ], limit=1)

                                    if product:
                                        boi_id = request.env['mrp.bom'].sudo().search([
                                        ('product_tmpl_id', '=', product.id)],limit=1)
                                        if boi_id:
                                            boi_id_lines = request.env['mrp.bom.line'].sudo().search([('bom_id', '=', boi_id.id)])
                                            if boi_id_lines:
                                                for line in boi_id_lines:   #pr_data = [0,0,{'product_id': i['id'],'product_uom_qty': i['qty']  }]
                                                    product_id = line.product_id.id
                                                    product_uom_qty = line.product_qty
                                                    free_qty=line.free_qty
                                                    unit_price=line.unit_price

                                                    # Add regular product line
                                                    if product_language =="ar":
                                                        product_combo_name =product.arabic_name
                                                    else:
                                                        product_combo_name =product.name


                                                    ProductList.append({
                                                        "id": product_id,
                                                        "qty": product_uom_qty,
                                                        "unit_price": unit_price,
                                                        "discount": "0%",  # Use string to indicate percentage
                                                        "combo_product_name": product_combo_name
                                                    })

                                                    # Add free quantity line if exists
                                                    if free_qty:
                                                        ProductList.append({
                                                            "id": product_id,
                                                            "qty": free_qty,
                                                            "unit_price": 0,
                                                            "discount": "100%",  # Free product, 100% discount
                                                            "combo_product_name": product_combo_name
                                                        })
                                    else:
                                        continue
                                else:
                                    continue  
                            if not ProductList:
                                continue
                            
                            customer_info = orderdata.get("customersOrgDetail", {})
                            customer_name = customer_info.get("name")

                            #  If name is None or empty, fallback to first uniqueName
                            if not customer_name:
                                unique_names = customer_info.get("uniqueName", [])
                                if isinstance(unique_names, list) and unique_names:
                                    customer_name = unique_names[0]
                                else:
                                    customer_name = "Unknown Customer"

                            customer_mobile = orderdata["customersOrgDetail"]["mobileNo"]

                            customer_address = orderdata["customerorgaddressDetail"][0]["addreshObject"]

                            region = customer_address.get('region','AL Jahra')
                            print("region....",region)
                            city = customer_address.get('city')
                            street = customer_address.get('street')
                           
                            # Extract fields
                            fields_order = ['house', 'block', 'floorNumber', 'apartmentNumber', 'officeNumber', 'buildlingName', 'street']
                            address_parts = []

                            for field in fields_order:
                                value = customer_address.get(field)
                                if value:  # skip None or empty values
                                    address_parts.append(str(value).strip())

                            # Final full address
                            full_street = ', '.join(address_parts)


                            # state = request.env['res.country.state'].sudo().search([
                            #     ('name', '=', region)
                            # ], limit=1)
                            country = request.env['res.country'].sudo().search([
                                ('name', '=', "Oman")
                            ], limit=1)

                            region_code = region[:3].upper().strip()

                            State = request.env['res.country.state'].sudo()
                            print("state....0909090",State)
                            state = State.search([
                                    ('country_id', '=', country.id),
                                    ('code', '=', region_code)
                                ], limit=1)
                            
                            print("state....",state)
                            if not state:
                                state = State.create({
                                    'name': region,
                                    'code': region_code,
                                    'country_id': country.id,
                                })
                            print("state..........3232..",state)
                            partner = request.env['res.partner'].sudo().search([
                                ('mobile', '=', customer_mobile)
                            ], limit=1)

                            # If not found, create customer with default address

                            if not partner:
                                # Create new partner
                                partner = request.env['res.partner'].sudo().create({
                                    'name': customer_name,
                                    'mobile': customer_mobile,
                                    'street': full_street,
                                    'city': city,
                                    'state_id': state.id if state else False,
                                    'country_id': country.id if country else False,
                                })
                            else:
                                # Update existing partner
                                partner.write({
                                    'name': customer_name,
                                    'mobile': customer_mobile,
                                    'street': full_street,
                                    'city': city,
                                    'state_id': state.id if state else False,
                                    'country_id': country.id if country else False,
                                })
    

                            #  Get customer ID
                            customer_id = partner.id
                            print("Customer ID:", customer_id)

                            partner_id = customer_id
                            product_name = ProductList
                            uid = 2

                            if not uid:
                                return {
                                    "ErrorCode": 400,
                                    'status': 'error',
                                    "Successfully": False,
                                    "message":"Please provide vendor detail.",
                                }
                            
                            else:

                                sale_order_line = []
                                for i in product_name:
                                    # Clean and convert unit_price and discount
                                    unit_price = float(i['unit_price']) if isinstance(i['unit_price'], str) else i['unit_price']
                                    discount = float(i['discount'].replace('%', '')) if isinstance(i['discount'], str) else i['discount']

                                    pr_data = [0, 0, {
                                        'product_id': i['id'],
                                        'product_uom_qty': float(i['qty']),
                                        'price_unit': unit_price,
                                        'discount': discount,
                                        "combo_product_name": i['combo_product_name']
                                    }]
                                    sale_order_line.append(pr_data)

                                sale_order_data = {
                                    'user_id': uid,
                                    'payment_term_id': 1,
                                    'partner_id': partner_id,
                                    'order_line': sale_order_line,
                                    'whatsapp_sale_order_id': orderdata["_id"],
                                    'language_name': product_language
                                }

                                sale_order = request.env['sale.order'].sudo().create(sale_order_data)
                                
                                invoice_data = {
                                                'move_type': 'out_invoice',
                                                'partner_id': sale_order.partner_id.id,
                                                'invoice_origin': sale_order.name,
                                                'invoice_line_ids': [
                                                    (0, 0, {
                                                        'product_id': line.product_id.id,
                                                        'quantity': line.product_uom_qty,
                                                        'price_unit': line.price_unit,
                                                        'discount': line.discount,
                                                        'tax_ids': [(6, 0, [])],  # Disable all taxes
                                                        "combo_product_name": line['combo_product_name']
                                                    })
                                                    for line in sale_order.order_line
                                                ]
                                            }

                                invoice = request.env['account.move'].sudo().create(invoice_data)
                                print("invoice",invoice)

                                sale_order.write({'invoice_ids': [(4, invoice.id)]})
                                
                                # Fetch required fields from account.move.line
                                account_move_lines = request.env['account.move.line'].sudo().search_read(
                                    [('move_id', '=', invoice.id), ('display_type', '=', "product")],
                                    ['id']
                                )

                                # Fetch required fields from sale.order.line
                                sale_order_lines = request.env['sale.order.line'].sudo().search_read(
                                    [('order_id', '=', sale_order.id)],
                                    ['id']
                                )

                                # Zip the data to merge
                                merged_data = [
                                    {"Account_id": acc_line['id'], "order_id": order_line['id']}
                                    for acc_line, order_line in zip(account_move_lines, sale_order_lines)
                                ]

                                # Bulk insertion
                                if merged_data:
                                    query = """
                                        INSERT INTO sale_order_line_invoice_rel (invoice_line_id, order_line_id)
                                        VALUES {}
                                    """.format(", ".join("(%s, %s)" % (values["Account_id"], values["order_id"]) for values in merged_data))

                                    # Execute the query
                                    request.env.cr.execute(query)
                                    # Commit the transaction
                                    request.env.cr.commit()

                                sale_order.action_confirm()   #conform sales order 

                                invoice.action_post()  #conform invoice 

                                payment_register = request.env['account.payment.register'].with_context(active_model='account.move', active_ids=invoice.ids).sudo().create({
                                    'payment_date': fields.Date.today(),
                                    'journal_id': request.env['account.journal'].sudo().search([('type', '=', 'bank')], limit=1).id,
                                    'amount': invoice.amount_total,
                                    'payment_method_line_id': request.env['account.payment.method.line'].sudo().search([
                                        ('payment_method_id.payment_type', '=', 'inbound'),
                                        ('journal_id.type', '=', 'bank')
                                    ], limit=1).id
                                })
                                payment_register.sudo().action_create_payments()
                                
                    data= {
                        "status_code": "200",
                        'message': 'Data created successfully'
                        }
                    return Response(
                    json.dumps(data),
                    content_type='application/json',
                    status=200
                        )  
                
            data= {
                    "status_code": "200",
                    'message': 'Data already exist'
                    }
            return Response(
                    json.dumps(data),
                    content_type='application/json',
                    status=200
                )  
        except AttributeError:
            return Response(
                            json.dumps(data),
                            content_type='application/json',
                            status=400)

        except Exception as e:

            data= {
                'status': 'error',
                "status_code": "400",
                'message': str(e)
                }
            return Response(
                            json.dumps(data),
                            content_type='application/json',
                            status=400)    

class CreateLead(http.Controller):

    @http.route('/CreateLead', type='http', auth='public', methods=['POST'], csrf=False)
    def create_lead(self, **post):
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            print("data.........", data)

            partner_name = data.get("customerName")
            phone = data.get("mobileNo")
            message = data.get("message")

            file_url = data.get("msgfile")
            file_type = data.get("fileType")  # e.g. "audio/mpeg"
            msg_type = data.get("msgType")    # optional custom type
            ticketId = data.get("ticketId") 
            customerId = data.get("customerId") 
            userId = data.get("userId") 

            Partner = http.request.env['res.partner'].sudo()
            partner = Partner.search([('mobile', '=', phone)], limit=1)

            if partner:
                #  Update existing partner
                partner.write({
                    'chatactive': True,
                    'chat_activated_at': fields.Datetime.now(),
                    'ticketId': ticketId,
                    'customerId':customerId,
                    'userId':userId
                })
            else:
                #  Create new partner
                partner = Partner.create({
                    'name': partner_name or 'Unknown',
                    'mobile': phone,
                    'chatactive': True,
                    'chat_activated_at': fields.Datetime.now(),
                    'ticketId': ticketId,
                    'customerId':customerId,
                    'userId':userId
                })

            msg_vals = {
                'partner_id': partner.id,
                'message': message,
                'is_from_user': False,
            }

            #  Download file & convert to Base64
            if file_url:
                try:
                    response = requests.get(file_url)
                    if response.status_code == 200:
                        file_content = base64.b64encode(response.content).decode('utf-8')
                        msg_vals.update({
                            'attachment_name': file_url.split('/')[-1],
                            'attachment_data': file_content,
                            'attachment_type': msg_type or self._detect_type(file_type),
                        })
                    else:
                        print(f" Failed to download file: {file_url} — {response.status_code}")
                except Exception as e:
                    print(f" Error downloading file: {e}")

            new_message = request.env['whatsapp.chat.message'].sudo().create(msg_vals)

            channel = "RefreshwhatsappPage"
            message= {"refresh": True}
            datasets= request.env['bus.bus']._sendone(channel, 'Refresh_whatsapp_Page', message)

            return http.Response(
                json.dumps({
                    "status": "success",
                    "message_id": new_message.id,
                    "message": "Message saved successfully"
                }),
                content_type="application/json",
                status=200
            )

        except Exception as e:
            print("error......",e)
            return http.Response(
                json.dumps({"status": "error", "message": str(e)}),
                content_type="application/json",
                status=500
            )

    # Detects correct file type based on MIME
    def _detect_type(self, mime_type):
        if not mime_type:
            return 'document'
        mime_type = mime_type.lower()
        if 'image' in mime_type:
            return 'image'
        elif 'video' in mime_type:
            return 'video'
        elif 'audio' in mime_type:
            return 'audio'
        else:
            return 'document'
    
        
class TemplateWebhook(http.Controller):

    @http.route('/TemplateWebhook', type='http', auth='public', methods=['POST'], csrf=False)
    def create_temp(self, **post):
        try:
            # Read raw JSON body
            data = json.loads(request.httprequest.data.decode('utf-8'))
            create_template_controller = CreateTemplate()
            dataset=create_template_controller.create_template(**data)
            return request.make_response(
                json.dumps({
                    'status': 'success',
                    'error_code': '200',
                    'message': 'Data received successfully!'
                }),
                headers=[('Content-Type', 'application/json')]
            )

        except Exception as e:
            return request.make_response(
                json.dumps({
                    'status': 'error',
                    'error_code': '400',
                    'message': f'An error occurred: {str(e)}'
                }),
                headers=[('Content-Type', 'application/json')])
        


class CreateTemplate(http.Controller):

    @http.route('/CreateTemplate', type='http', auth='public', methods=['GET'], csrf=False)
    def create_template(self, **kwargs):
        try:
            # Get Org info from system parameters
            setting_object = request.env["ir.config_parameter"].sudo()
            org_id = setting_object.get_param("org_id")
            go4whatsapp_access_token = setting_object.get_param("go4whatsapp_access_token")  
            go4whatsapp_url = setting_object.get_param("go4whatsapp_url")  
            org_id="6765502fea01d8b323ef9547"
            # API Call
            url = f"{go4whatsapp_url}/getAllTemplatedBtOrgId"
            payload = json.dumps({
                "orgId": org_id,
                "limit": 50,
                "skipData": 0,
                "status": ["APPROVED","REJECTED"],
                "search": "",
                "templateType": "normal",
                "isManageTemplate": True
            })
            
            headers = {'Content-Type': 'application/json'}
            response = requests.request("POST", url, headers=headers, data=payload)
            result = response.json()
           
            # Validate templates list
            templates = result.get("getAllTemplatedBtOrgId", [])
            if not templates:
                return request.make_response(
                    json.dumps({
                        'status': 'error',
                        'error_code': '204',
                        'message': 'No template data found!'
                    }),
                    headers=[('Content-Type', 'application/json')]
                )

            TemplateModel = request.env["whatsapp.template"].sudo()
            created, updated = 0, 0

            for t in templates:
                # --- Safely parse templateDesign ---
                print("t.................",t)
                design_raw = t.get("templateDesign") or {}
                if isinstance(design_raw, str):
                    try:
                        design = json.loads(design_raw)
                    except Exception:
                        design = {}
                else:
                    design = design_raw

                # --- Safely parse templatedObject ---
                templated_obj_raw = t.get("templatedObject") or {}
                templated_obj = templated_obj_raw if isinstance(templated_obj_raw, dict) else {}

                # --- Extract components ---
                components = templated_obj.get("components") or []

                # --- Safely parse extraObject ---
                extra_obj_raw = templated_obj.get("extraObject") or {}
                if isinstance(extra_obj_raw, str):
                    try:
                        extra_obj = json.loads(extra_obj_raw)
                    except Exception:
                        extra_obj = {}
                else:
                    extra_obj = extra_obj_raw

                # --- Extract texts ---
                body_text = design.get("body_text")
                footer_text = design.get("footer_text")
                header_type = design.get("header_type")

                # If not found in design, look inside components
                if not body_text:
                    for comp in components:
                        if comp.get("type") == "BODY":
                            body_text = comp.get("text")
                        elif comp.get("type") == "FOOTER":
                            footer_text = comp.get("text")

                # --- Prepare vals for Odoo model ---
                vals = {
                    "template_id": t.get("_id"),
                    "org_id": t.get("orgId"),
                    "template_name": t.get("templateName"),
                    "language": t.get("language"),
                    "category01": t.get("category").lower(),
                    "status": t.get("status"),
                    "is_active": t.get("isActive", True),
                    "is_delete": t.get("isDelete", False),
                    "template_type": t.get("templateType"),
                    "is_verified": t.get("isVerified", False),
                    "template_utility": t.get("templateUtility"),
                    "is_display": t.get("isDisplay", True),
                    "body_text": body_text,
                    "footer_text": footer_text,
                    "header_type": header_type,
                    "header_image": design.get("header_image"),
                    "first_quick_button": design.get("firstQuickButton"),
                    "second_quick_button": design.get("secondQuickButton"),
                    "third_quick_button": design.get("thirdQuickButton"),
                    "quick_btn_length": design.get("quickBtnLength"),
                    "btn_url_text": design.get("btnUrlText"),
                    "btn_phone_number_text": design.get("btnPhoneNumberText"),
                    "template_design_json": json.dumps(design),
                    "templated_object_json": json.dumps(templated_obj),
                    "components_json": json.dumps(components),
                    "extra_object_json": json.dumps(extra_obj),
                    "templated_keyword_datas": json.dumps(t.get("templatedkeywordDatas", [])),
                }

                # --- Create or Update record ---
                existing = TemplateModel.search([("template_name", "=", t.get("templateName"))], limit=1)
                if existing:
                    existing.write(vals)
                    updated += 1
                else:
                    TemplateModel.create(vals)
                    created += 1

            # --- Success Response ---
            return request.make_response(
                json.dumps({
                    'status': 'success',
                    'error_code': '200',
                    'message': f'{created} created, {updated} updated successfully!'
                }),
                headers=[('Content-Type', 'application/json')]
            )

        except Exception as e:
            print("......",e)
            return request.make_response(
                json.dumps({
                    'status': 'error',
                    'error_code': '400',
                    'message': f'An error occurred: {str(e)}'
                }),
                headers=[('Content-Type', 'application/json')]
            )


class CheckReadRecipt(http.Controller):

    @http.route('/CheckMessagesRecipts', type='http', auth='public', methods=['POST'], csrf=False)
    def create_lead(self, **post):
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            print("CheckMessagesRecipts.........", data)

            if data.get('messageStatus') in ['read', 'delivered']:
                    messageStatus= data.get('messageStatus')
                    customerMobileNo= data.get('customerMobileNo')
                    print(messageStatus,customerMobileNo)
                    Partner = http.request.env['res.partner'].sudo()
                    partner = Partner.search([('mobile', '=', customerMobileNo)], limit=1)
                    if not partner:
                        return http.Response(
                            json.dumps({
                                "status": "error",
                                "message": "Message not saved successfully"
                            }),
                            content_type="application/json",
                            status=400
                        )

                    Message = request.env["whatsapp.chat.message"].sudo()
                    messages = Message.search([("partner_id", "=", partner.id)])
                    try:
                        if messageStatus == "delivered":
                            messages.write({
                                "single_tick": True,
                                "double_tick": True
                            })

                        if messageStatus == "read":
                            messages.write({
                                "single_tick": True,
                                "double_tick": True,
                                "read_cust_message": True
                            })
                    except:
                        pass    

                    else:
                        pass    

            else:
                print("Message not read or delivered")

            channel = "RefreshwhatsappPage"
            message= {"refresh": True}
            datasets= request.env['bus.bus']._sendone(channel, 'Refresh_whatsapp_Page', message)

            return http.Response(
                json.dumps({
                    "status": "success",
                    "message": "Message saved successfully"
                }),
                content_type="application/json",
                status=200
            )

        except Exception as e:
            print("error......",e)
            return http.Response(
                json.dumps({"status": "error", "message": str(e)}),
                content_type="application/json",
                status=500
            )



class SubscriptionWebhook(http.Controller):

    @http.route('/NotifypaymentfromSubscription', type='http', auth='public', methods=['POST'], csrf=False)
    def subscription_webhook(self, **post):
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            print("Webhook Data Received:", data)

            odoo_pkg = data

            # ------------------------------  
            # FIXED DATE CLEANER (Working)
            # ------------------------------  
            def clean_date(date_string):
                if not date_string:
                    return False
                date_string = date_string.replace("Z", "")
                date_string = date_string.replace("T", " ")
                if "." in date_string:
                    date_string = date_string.split(".")[0]
                return date_string

            expiry_date_str = clean_date(odoo_pkg.get("expiryDate"))
            subscription_date_str = clean_date(odoo_pkg.get("subscriptionDate"))

            expiry_date = fields.Datetime.from_string(expiry_date_str) if expiry_date_str else False
            subscription_date = fields.Datetime.from_string(subscription_date_str) if subscription_date_str else False

            # CREATE RECORD  
            request.env['whatsapp.payment.wizard'].sudo().create({
                'amount': odoo_pkg.get("price"),
                'payment_link_id': odoo_pkg.get("paymentgatwayId"),
                'user_id': odoo_pkg.get("orgId"),
                'status': 'done',
                'payment_status': 'success',
                'start_datetime': subscription_date,
                'end_datetime': expiry_date,
                'subscription_id': odoo_pkg.get("subscriptionID"),
            })

            return request.make_response(
                json.dumps({
                    'status': 'success',
                    'error_code': 200,
                    'message': 'Subscription data stored successfully!'
                }),
                headers=[('Content-Type', 'application/json')]
            )

        except Exception as e:
            print("Webhook Error >>", str(e))
            return request.make_response(
                json.dumps({
                    'status': 'error',
                    'error_code': 400,
                    'message': f'An error occurred: {str(e)}'
                }),
                headers=[('Content-Type', 'application/json')]
            )