# -*- coding: utf-8 -*-
{
    'name': 'Anabtawi Sales Visit Tracking',
    'version': '19.0.2.0.0',
    'summary': 'Simplified Sales representative customer visits tracking, geofence check-ins, and routing.',
    'description': """
Anabtawi Sales Visit Tracking Module - Full Step-by-Step Workflow
================================================================

The module implements a simplified workflow designed for non-technical salespeople, learnable in under 5 minutes:

Step-by-Step Salesperson Workflow:
----------------------------------
1. **View Today's Leads**: The salesperson opens the single-page mobile app in Odoo and views all assigned leads for the day under "My Daily Visits".
2. **Navigate**: They click "Navigate" on a lead card to open Google Maps navigation to the customer's coordinates.
3. **Arrival & Check-In**: Upon arrival at the customer's location, they click "Start Visit". The system captures their GPS coordinates, verifies geofencing validation (Valid: <= 100m, Warning: 101-300m, Invalid: > 300m), and starts an active visit timer.
4. **End Visit**: After conducting the visit, they click "End Visit". The system captures the checkout GPS coordinates and stops the timer.
5. **Select Outcome**: They choose one of the three simplified outcomes:
   - **Approved**: Prompts to save and automatically converts the lead into a standard Odoo Contact (res.partner).
   - **Revisit**: Prompts the user to select the "Next Visit Date" and updates the schedule.
   - **Rejected**: Prompts the user to select a "Rejection Reason" (Price, Competitor, Not Interested, No Budget, or Other) and logs it.

Manager & Supervisor Features:
------------------------------
- **KPI Dashboard**: View real-time visits, GPS compliance percentage, active representatives, and outcomes.
- **Live Route Tracking Map**: Display customers, check-in markers with verification status, and background route travel points.
    """,
    'category': 'Sales',
    'author': 'Anabtawi Group',
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
        'data/ir_cron_data.xml',
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
