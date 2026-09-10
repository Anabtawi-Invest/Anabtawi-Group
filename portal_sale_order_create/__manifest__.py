# -*- coding: utf-8 -*-
{
    "name": "Portal Sale Order Create",
    "summary": "Sales Portal: create sale orders, auto-invoice, print/email/WhatsApp, cancel & list own orders",
    "version": "19.0.1.0.4",
    "category": "Sales/Portal",
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": [
        "portal",
        "sale_management",
        "account",
        "product",
    ],
    "data": [
        "security/security.xml",
        "views/portal_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "portal_sale_order_create/static/src/css/portal_sale_order.css",
            "portal_sale_order_create/static/src/js/portal_sale_order.js",
        ],
    },
    "installable": True,
    "application": False,
}
