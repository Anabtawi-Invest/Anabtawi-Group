{
    'name': 'HR Employee Number Search',
    'version': '19.0.1.0.7',
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
        'point_of_sale',
    ],
    'data': [
        'views/hr_employee_search_views.xml',
        'views/hr_employee.xml',
        'views/res_partner_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'hr_employee_code/static/src/app/models/res_partner_patch.js',
            'hr_employee_code/static/src/app/screens/partner_list/partner_list_patch.js',
        ],
    },
    'installable': True,
    'application': False,
    'post_init_hook': 'post_init_hook',
}
