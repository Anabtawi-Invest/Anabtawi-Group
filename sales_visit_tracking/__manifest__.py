# -*- coding: utf-8 -*-
{
    'name': 'Anabtawi Sales Visit Tracking',
    'version': '19.0.2.0.0',
    'summary': 'Simplified Sales representative customer visits tracking, geofence check-ins, and routing.',
    'description': """
Anabtawi Sales Visit Tracking Module
====================================
This module implements the simplified Anabtawi Sales Visit Workflow:
- Single-page mobile app for salespeople to view today's leads, click navigate, check in, and record check-out outcomes.
- Simple outcomes: Revisit, Approved (converts lead to Contact), and Rejected (rejection reason).
- Background route logging for managers.
- Advanced KPIs manager dashboard and route tracking map.
    """,
    'category': 'Sales',
    'author': 'Anabtawi Group',
    'website': 'https://www.anabtawi.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'sale',
        'contacts',
        'hr',
        'planning',
        'fleet',
        'documents',
        'approvals',
        'mail',
        'calendar',
    ],
    'data': [
        'security/sales_visit_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/res_config_settings_views.xml',
        'views/res_partner_views.xml',
        'views/sales_visit_lead_views.xml',
        'views/sales_visit_views.xml',
        'views/sales_route_point_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sales_visit_tracking/static/lib/leaflet/leaflet.css',
            'sales_visit_tracking/static/lib/leaflet/leaflet.js',
            'sales_visit_tracking/static/src/scss/map.scss',
            'sales_visit_tracking/static/src/scss/dashboard.scss',
            'sales_visit_tracking/static/src/scss/mobile_app.scss',
            'sales_visit_tracking/static/src/components/map/map.js',
            'sales_visit_tracking/static/src/components/map/map.xml',
            'sales_visit_tracking/static/src/components/dashboard/dashboard.js',
            'sales_visit_tracking/static/src/components/dashboard/dashboard.xml',
            'sales_visit_tracking/static/src/components/mobile_app/mobile_app.js',
            'sales_visit_tracking/static/src/components/mobile_app/mobile_app.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
