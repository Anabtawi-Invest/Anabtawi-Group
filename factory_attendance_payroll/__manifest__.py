{
    'name': 'Factory Attendance & Payroll Reconciliation',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Automatic multi-location break deduction, daily attendance monitoring, planning shift integration, and 3-Step Lateness Settlement.',
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
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
