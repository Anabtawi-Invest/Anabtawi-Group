# -*- coding: utf-8 -*-
{
    'name': "WhatsApp Business API Odoo | WhatsApp API Integration | Odoo WhatsApp API Integration | Odoo WhatsApp API",

    'summary': """
       WhatsApp Business API Integration for Odoo, Powered by Go4whatsup – Official, Secure & Automated , Send quotations, invoices, delivery updates, and payment notifications directly from Odoo to your customers on WhatsApp — automatically and compliantly.
        Go4whatsup WhatsApp Odoo Connector integrates Odoo with the official WhatsApp Business API, allowing businesses to automate customer communication inside their ERP without technical complexity.
    """,

    'description': """
        WhatsApp Business API Integration for Odoo, Powered by Go4whatsup – Official, Secure & Automated , Send quotations, invoices, delivery updates, and payment notifications directly from Odoo to your customers on WhatsApp — automatically and compliantly.
        Go4whatsup WhatsApp Odoo Connector integrates Odoo with the official WhatsApp Business API, allowing businesses to automate customer communication inside their ERP without technical complexity.
    """,
    'author': "Inwizards software Technology Pvt Ltd",
    'website': "https://www.inwizards.com/",
    'category': 'Extra Tools',
    'version': '19.1',
    'depends': ['base', 'sale','bus','web'], 
    "license": "AGPL-3",
    'live_test_url': 'https://pos.onlineemenu.com/web/login?db=pos_emenu2&du=test',
    'data': [
        'security/ir.model.access.csv',
        'views/installation_popup_view.xml',
        'views/dashboard_action.xml',
        'views/menu.xml',
        'views/sale_order_inherit.xml',
        'views/whatsapp_template.xml',
        'views/menu_whatspp_trigger.xml',
        'data/data.xml',
        'data/cron_job.xml',
        'views/cancel_subscription.xml',
        'views/help_wizard_view.xml',
        'views/otp_validate_view.xml',
        'views/views.xml',
        'views/registration_form.xml',
        'views/payment_conform.xml',
        'views/whatsapp.xml',
        'views/res_config.xml',
        'views/mrp_bom_line.xml',
        'views/whatsapp_payment_wizards.xml',
        'views/menu_inherit.xml',
        'views/help_page.xml',
        'views/sale_order_line_view.xml',
        # 'views/stock_picking_view.xml',
        'views/account_move_view.xml',
        
    ],
    'assets': {
        'web.assets_backend': [
            'whatsapp_api_odoo03/static/src/js/whatsapp_chat_button.js',     
            'whatsapp_api_odoo03/static/src/js/dashboard.js',   
            'whatsapp_api_odoo03/static/src/xml/dashboard.xml',     
            "whatsapp_api_odoo03/static/src/xml/whatsapp_chat_button.xml",
            "whatsapp_api_odoo03/static/src/css/whatsapp_chat_button.css",
        ],
    },
   "images" : ['static/description/connector3.gif']
}

