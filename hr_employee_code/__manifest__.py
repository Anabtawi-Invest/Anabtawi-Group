{
    'name': 'HR Employee Number Search',
    'version': '19.0.1.0.0',
    'summary': 'Make employee number searchable across HR views.',
    'category': 'Human Resources',
    'author': 'Rana Faris',
    'license': 'LGPL-3',
    'depends': [
        'hr',
        'hr_attendance',
        'hr_holidays',
        'hr_expense',
        'hr_recruitment',
        'hr_skills',
        'hr_work_entry',
    ],
    'data': [
        'views/hr_employee_search_views.xml',
    ],
    'installable': True,
    'application': False,
}
