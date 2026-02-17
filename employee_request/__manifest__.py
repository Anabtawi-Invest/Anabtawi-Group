# -*- coding: utf-8 -*-
{
    "name": "Employee Request",
    "version": "19.0.1.0.0",
    "category": "Human Resources",
    "summary": "Base module for employee requests (skeleton).",
    "author": "",
    "license": "LGPL-3",
    "depends": ["base", "hr", "point_of_sale"],
    "data": [
        "security/ir.model.access.csv",
        "data/employee_request_cron.xml",
        "views/employee_request_views.xml",
        "views/pos_config_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "employee_request/static/src/fields/password_eye_char_field.js",
            "employee_request/static/src/fields/password_eye_char_field.xml",
        ],
        "point_of_sale._assets_pos": [
            "employee_request/static/src/pos/employee_password_popup.js",
            "employee_request/static/src/pos/employee_password_popup.xml",
            "employee_request/static/src/pos/employee_pricelist_password_validation.js",
        ],
    },
    "installable": True,
    "application": False,
}

