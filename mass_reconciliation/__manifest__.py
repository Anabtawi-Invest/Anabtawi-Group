# -*- coding: utf-8 -*-
{
    'name': 'Mass Reconciliation',
    'summary': 'Covers lateness using overtime then annual leave then salary deduction (no OT bank).',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'author': 'Softobia',
    'depends': ['hr_payroll', 'hr_holidays'],
    'data': [
        'security/ir.model.access.csv',
        'data/payslip_input_type.xml',
        'data/server_actions.xml',
    ],
    'installable': True,
    'application': False,
}
