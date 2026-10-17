# -*- coding: utf-8 -*-
{
    'name': 'Jordan AR/3 Payroll Report',
    'summary': 'Jordan Income & Sales Tax AR/3 (PWTS) salary and withholding certificate',
    'description': """
Jordan AR/3 Report
==================
Generates the official Payroll and Withholding Tax Statement (AR/3) certificate
from employee legal name fields and validated/paid payslips.

* PDF and Excel export
* Configurable gross salary and income tax salary rules per company
* Legal name fields on the employee form (Jordan)
    """,
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'author': 'Custom Solutions',
    'license': 'LGPL-3',
    'depends': [
        'hr_payroll',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/payroll_report_wizard_views.xml',
        'views/hr_employee_views.xml',
        'views/res_config_settings_views.xml',
        'views/payroll_menus.xml',
        'report/report_templates.xml',
        'report/report_action.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
