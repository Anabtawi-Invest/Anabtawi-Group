{
    'name': 'planning Enhancement',
    'version': '19.0.1.0.4',
    'summary': 'Cover lateness using OT buckets then Annual Leave (hours) then remaining lateness for payroll deduction. No OT Bank.',
    'category': 'Human Resources/Payroll',
    "author":"Anabtawi",
    'license': 'LGPL-3',
    'depends': [
        'hr_payroll',
        'hr_holidays',
        'hr_attendance',
        'hr_holidays_attendance',
        'planning',
    ],
    'data': [
        'views/planning_slot_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
}
