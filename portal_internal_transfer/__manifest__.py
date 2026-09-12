# -*- coding: utf-8 -*-
{
    "name": "Portal Internal Transfer",
    "summary": "Portal card to create, confirm, list and cancel stock internal transfers",
    "version": "19.0.1.0.1",
    "category": "Inventory/Portal",
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": [
        "portal",
        "stock",
        "product",
    ],
    "data": [
        "security/security.xml",
        "views/portal_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "portal_internal_transfer/static/src/css/portal_internal_transfer.css",
            "portal_internal_transfer/static/src/js/portal_internal_transfer.js",
        ],
    },
    "installable": True,
    "application": False,
}
