# -*- coding: utf-8 -*-
{
    'name': 'Reconciliation Payroll',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Unified attendance reconciliation, 3-step lateness settlement, flexible/fixed rest day quotas, and schedule-aware payroll.',
    'author': 'Anabtawi Group',
    'license': 'OPL-1',
    'depends': [
        'hr_payroll',
        'hr_attendance',
        'hr_work_entry',
        'hr_holidays',
    ],
    'data': [
        'data/work_entry_type_data.xml',
        'data/hr_payroll_data.xml',
        'data/ir_cron_data.xml',
        'views/hr_attendance_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_payslip_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
