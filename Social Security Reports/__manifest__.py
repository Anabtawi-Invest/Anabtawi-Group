# -*- coding: utf-8 -*-
{
    'name': 'Social Security Reports',
    'version': '19.0.1.0.0',
    'summary': 'Jordanian Social Security Reports (Add New & Terminate Employees) in PDF and Excel',
    'description': """
تقارير الضمان الاجتماعي الأردني:
1. إضافة موظفين جدد إلى الضمان الاجتماعي (PDF & Excel)
2. إنهاء / استبعاد موظفين من الضمان الاجتماعي (PDF & Excel)
مطابق تماماً لنماذج المؤسسة العامة للضمان الاجتماعي وشركة العنبتاوي.
    """,
    'category': 'Human Resources/Payroll',
    'author': 'Anabtawi Group / AGY Assistant',
    'website': 'https://anabtawisweets.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'hr',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/social_security_report_wizard_views.xml',
        'views/menu_views.xml',
        'report/report_actions.xml',
        'report/report_social_security_new_template.xml',
        'report/report_social_security_terminated_template.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
