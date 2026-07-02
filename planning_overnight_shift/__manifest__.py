{
    'name': 'Planning Overnight Shift Support',
    'version': '19.0.1.0.0',
    'summary': 'Allows shift templates to span overnight across midnight (e.g. 15:00 to 01:00) with 12h AM/PM selection and bypasses one-day shift constraints.',
    'category': 'Human Resources/Planning',
    'author': 'Anabtawi',
    'license': 'LGPL-3',
    'depends': [
        'planning',
    ],
    'data': [
        'views/planning_template_views.xml',
    ],
    'installable': True,
    'application': False,
}
