# -*- coding: utf-8 -*-
{
    "name": "POS Employee Due Limit",
    "version": "19.0.1.0.2",
    "category": "Point of Sale",
    "summary": "Limit employees' Customer Account due in POS to a percentage of their net wage",
    "description": """
POS Employee Due Limit
======================

The credit limit (Partner Limit) of each employee's Work Contact is filled
automatically from the employee's wage:

    limit = (wage - wage * deduction %) * max due %

Both percentages are configured per company in Point of Sale settings.
The limit is refreshed when the wage, the work contact or the settings change,
and every day by a scheduled action.

When a POS order is paid with Customer Account for an employee, the order is
blocked if the employee's current due plus the order amount exceeds the limit.
Employees without a wage cannot buy on Customer Account.
    """,
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "hr", "pos_settle_due"],
    "data": [
        "data/ir_cron_data.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "anabtawi_pos_employee_due_limit/static/src/app/order_payment_validation_patch.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
