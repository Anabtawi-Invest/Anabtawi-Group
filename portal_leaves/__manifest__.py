# -*- coding: utf-8 -*-
{
    'name': "SW - Leaves Portal",
    'summary': "Portal users can access their time off requests and create new time off requests",
    'description': """
     _ Adds a "Time Off" dashboard showing employee leave details, request status, and a quick link to create new requests.
     _ Portal users can submit and track their time off requests, while managers have access to a dedicated "Time Off to Approve" menu displaying all pending employee requests for validation, approval, or refusal.
    """,
    'category': 'Portal',
    'author': "Enbtawi Sweet",
    'website': "Enbtawi Sweet",
    'version': '1.2',
    'depends': ['base', 'hr', 'hr_payroll', 'base_portal', 'hr_holidays', 'resource'],
    'data': [
        'security/ir.model.access.csv',
        'views/employee_portal.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'portal_leaves/static/src/js/employee_portal.js',
            'portal_leaves/static/src/js/script.js',
            'portal_leaves/static/src/scss/leave.scss',
        ],
    },
    'license': "Other proprietary",
}
