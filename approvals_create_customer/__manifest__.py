# -*- coding: utf-8 -*-
{
    "name": "Approvals - Create Customer",
    "summary": "Approval type to request new customers from portal; create res.partner on approve",
    "version": "19.0.1.0.2",
    "category": "Human Resources/Approvals",
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": [
        "approvals",
        "portal",
        "contacts",
    ],
    "post_init_hook": "post_init_hook",
    "data": [
        "security/security.xml",
        "data/approval_category_data.xml",
        "views/approval_request_views.xml",
        "views/portal_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "approvals_create_customer/static/src/css/portal_customer_request.css",
            "approvals_create_customer/static/src/js/portal_customer_request.js",
        ],
    },
    "installable": True,
    "application": False,
}
