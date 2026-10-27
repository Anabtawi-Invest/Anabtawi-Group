# -*- coding: utf-8 -*-
{
    'name': 'HR Accrual First-Month Proration',
    'version': '19.0.1.0.0',
    'summary': 'Prorate the first monthly time-off accrual by calendar days',
    'description': """
        Opt-in per accrual plan. The first monthly accrual of an allocation is
        monthly rate x eligible calendar days / days in month (joining day
        included). Later months accrue normally. Yearly caps are respected and
        the proration is applied once per allocation.
    """,
    'category': 'Human Resources/Time Off',
    'author': 'Anabtawi Group',
    'license': 'LGPL-3',
    'depends': ['hr_holidays', 'hr_enhancement_plan'],
    'data': [
        'views/hr_leave_accrual_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
