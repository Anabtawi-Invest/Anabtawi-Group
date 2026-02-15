# -*- coding: utf-8 -*-
{
    'name': 'Mass Reconciliation',
    'version': '19.0.1.0.0',
    'summary': 'Cover lateness using overtime then annual leave, without OT bank',
    'category': 'Human Resources/Payroll',
    'license': 'LGPL-3',
    'author': 'Softobia',
    'depends': ['hr_payroll', 'hr_holidays', 'hr_work_entry', 'hr_work_entry_holidays'],
    'data': [
        'security/ir.model.access.csv',
        'data/payslip_input_type.xml',
        'data/server_actions.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
