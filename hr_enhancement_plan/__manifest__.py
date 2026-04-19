# -*- coding: utf-8 -*-
{
    'name': 'HR Enhancement',
    'version': '1.0',
    'category': 'Human Resources',
    'summary': 'Accrual plan milestone from contract start and other HR enhancements',
    "author":"Anabtawi",
    'description': """
        Adds option to base leave accrual plan milestones on employee contract start date
        instead of allocation start date (e.g. "After 4 years" = 4 years from contract start).
    """,
    'depends': ['hr_holidays', 'hr'],
    'data': [
        'views/hr_leave_accrual_views.xml',
        'views/hr_leave_allocation_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
