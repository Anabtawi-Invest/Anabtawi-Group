# -*- coding: utf-8 -*-
{
    'name': 'Anabtawi Employee Profile PDF',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Employee profile PDF report and related HR fields',
    # hr_health_insurance: Anabtawi Group (new_pull21/Anabtawi-Group/hr_health_insurance)
    'depends': ['hr', 'hr_health_insurance'],
    'author': 'Anabtawi Group',
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_bank_views.xml',
        'views/hr_employee_views.xml',
        'views/menus.xml',
        'report/employee_profile_report.xml',
        'report/employee_profile_templates.xml',
    ],
    'installable': True,
    'application': False,
}
