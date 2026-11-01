# -*- coding: utf-8 -*-
{
    'name': 'Payroll Fix Recon - Negative Leave Allocation',
    'version': '19.0.2.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Allow negative leave allocations and integrate seamlessly with Payroll Fix Recon settlement and termination balances',
    'author': 'Anabtawi Group',
    'license': 'OPL-1',
    'depends': [
        'hr_holidays',
        'payroll_fix_recon',
    ],
    'data': [],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
