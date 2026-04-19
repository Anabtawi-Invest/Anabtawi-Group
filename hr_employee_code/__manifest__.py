{
    'name': 'hr.payslip_enhancement',
    'version': '19.0.1.0.4',
    'summary': 'Cover lateness using OT buckets then Annual Leave (hours) then remaining lateness for payroll deduction. No OT Bank.',
    'category': 'Human Resources/Payroll',
    "author":"Anabtawi",
    'license': 'LGPL-3',
    'depends': ['lateness_company_settings1', 'hr_payroll', 'hr_holidays', 'planning'],
    'data': [
        'views/hr_employee.xml',
    ],
    'installable': True,
    'application': False,
}
