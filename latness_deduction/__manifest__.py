{
    'name': 'hr.payslip_enhancement',
    'version': '19.0.1.0.4',
    'summary': 'Cover lateness using OT buckets then Annual Leave (hours) then remaining lateness for payroll deduction. No OT Bank.',
    'category': 'Human Resources/Payroll',
    'author': 'Rana Faris',
    'license': 'LGPL-3',
    'depends': [
        'lateness_company_settings1',
        'hr_payroll',
        'hr_holidays',
        'hr_attendance',
        'hr_holidays_attendance',
        'planning',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/server_actions.xml',
        'views/hr_employee_ot_conversion_views.xml',
        'views/hr_payslip_views.xml',
        'views/hr_payslip_input_views.xml',
        'views/planning_slot.xml',
        # Company lateness view last so res.company fields are registered first
        'views/res_config_settings_views.xml',
        'views/hr_employee.xml',
        'views/hr_employee_views.xml',

    ],
    'installable': True,
    'application': False,
}
