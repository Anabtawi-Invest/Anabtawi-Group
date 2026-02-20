{
    'name': 'hr.payslip_enhancement',
    'version': '19.0.1.0.1',
    'summary': 'Cover lateness using OT buckets then Annual Leave (hours) then remaining lateness for payroll deduction. No OT Bank.',
    'category': 'Human Resources/Payroll',
    'author': 'Anabtawi',
    'license': 'LGPL-3',
    'depends': ['hr_payroll', 'hr_holidays'],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_employee_views.xml',
        'views/hr_payslip_views.xml',
        'views/res_config_settings_views.xml',
        # 'data/server_actions.xml',
    ],
    'installable': True,
    'application': False,
}
