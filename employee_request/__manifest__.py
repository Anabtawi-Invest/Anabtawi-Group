# -*- coding: utf-8 -*-
{
    "name": "Employee Request",
    "version": "19.0.1.2.0",
    "category": "Human Resources",
    "summary": "Employee request and 5-minute Employee Portal OTP support.",
    "author":"Anabtawi",
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
    },
    "installable": True,
    "application": False,
}

