{
    "name": "Lateness Coverage Reconciliation (No OT Bank)",
    "version": "19.0.1.0.0",
    "category": "Payroll",
    "summary": "Automate lateness coverage using OT buckets then Annual Leave hours; remaining lateness for salary deduction (No OT Bank).",
    "author": "Anabtawi Invest",
    "license": "LGPL-3",
    "depends": ["hr_payroll", "hr_holidays"],
    "data": [
        "views/hr_payslip_views.xml",
                "views/res_config_settings_views.xml",
        "views/server_actions.xml"
    ],
    "installable": True,
    "application": False
}

