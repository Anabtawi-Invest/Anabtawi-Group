# -*- coding: utf-8 -*-
{
    'name': "SW - Base Portal",
    'summary': "Portal users can access their profiles",
    'description': "Ability to link portal users with the designated employee profile on the “HR Settings” tab.",
    'category': 'Portal',
    'author':'Anabtawi',
    'version': '1.0',
    'depends': ['base', 'hr', 'portal', 'hr_payroll', 'hr_holidays'],
    'data': [
        'views/employee_portal.xml',
        'views/employee_views.xml',
    ],
    'license': "Other proprietary",
}
