# -*- coding: utf-8 -*-
{
    'name': 'HR Allocation Contract Dates',
    'version': '19.0.1.0.0',
    'summary': 'Accrual allocation Start Date = contract start, End Date = contract end (standard accrual plan does the rest)',
    'description': """
        Keeps the standard Odoo accrual plan. Only the allocation dates are driven by the contract:
        - Start Date defaults to the employee's first contract start date, so the joining month is
          prorated by core Odoo.
        - End Date follows the contract end (termination) date every time the accrual runs, so the
          leaving month is prorated by core Odoo and nothing accrues afterwards.
    """,
    'category': 'Human Resources/Time Off',
    'author': 'Anabtawi Group',
    'license': 'LGPL-3',
    'depends': ['hr_holidays'],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
