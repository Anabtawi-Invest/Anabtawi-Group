{
    'name': 'Payroll Fix Recon',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Attendance reconciliation payroll: break policy, daily metrics, rest/absent engine, '
               '3-step lateness settlement and a single-source worked-days ledger.',
    'author': 'Anabtawi Group',
    'license': 'OPL-1',
    'depends': ['hr_payroll', 'hr_attendance', 'hr_work_entry', 'hr_holidays'],
    'data': [
        'data/ir_cron_data.xml',
        'views/hr_attendance_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_payslip_views.xml',
        'views/hr_work_entry_type_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
