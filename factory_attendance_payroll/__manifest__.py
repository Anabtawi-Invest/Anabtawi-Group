{
    'name': 'Factory Attendance & Payroll Reconciliation',
    'version': '19.0.2.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Multi-location break deduction, daily attendance monitoring, planning shift integration, and 3-Step Lateness Settlement for any Salary Structure.',
    'author': 'Custom Solutions',
    'license': 'OPL-1',
    'depends': [
        'hr_payroll',
        'hr_attendance',
    ],
    'data': [
        'data/hr_payroll_data.xml',
        'views/hr_payslip_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_attendance_views.xml',
    ],
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
