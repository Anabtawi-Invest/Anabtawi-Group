# -*- coding: utf-8 -*-
{
    'name': 'Anabtawi Sales Visit Tracking',
    'version': '19.0.2.0.0',
    'summary': 'Simplified Sales representative customer visits tracking, geofence check-ins, and routing.',
    'description': """
Anabtawi Sales Visit Tracking & Route Management (V2) - Complete Business Workflow
===================================================================================

This module implements a streamlined field sales tracking and routing system designed for Anabtawi Group.
It keeps the salesperson mobile interface extremely simple (learnable in under 5 minutes) while giving managers comprehensive dashboard analytics, live GPS validation, and immutable auditing.

1. SALESPERSON MOBILE WORKFLOW (OWL UI)
--------------------------------------
Salespeople open the responsive "My Daily Visits" dashboard directly on their mobile device:

- **Assigned Visits List**: Shows active, assigned customer or lead visits for the current day.
- **GPS Navigation**: A single button clicks out to external navigation maps using the partner/lead coordinates.
- **Lead Capture & Coordinate Locking**:
  * For New Leads (coordinates at 0.0), clicking "Save Location" captures the current GPS coordinates.
  * These coordinates are immediately **locked** on the lead record. Representative users cannot edit coordinates once locked; only Managers/Admins can modify them.
  * Saving the location automatically checks the salesperson in.
- **Strict Geofencing Check-In**:
  * For Existing Customers and Revisit Leads, clicking "Check In" calculates the distance between the salesperson's current coordinates and the registered customer coordinates.
  * **Strict 50-meter restriction**: If the salesperson is further than 50 meters from the destination, the check-in is **blocked** and throws a validation error.
  * A record of the blocked check-in attempt is logged in the system for supervisor review.
  * If within 50 meters, the check-in succeeds, transitioning the state to "In Progress" and tracking duration.
- **Simplified Outcomes (Max 3 actions per screen)**:
  * **For Leads**:
    - **[ Approved ]**: Converts the lead into a standard Odoo Customer Contact (res.partner) automatically.
    - **[ Revisit ]**: Prompts to choose a date and automatically schedules the next visit assignment.
    - **[ Rejected ]**: Prompts for a rejection reason (Price, Competitor, Not Interested, No Budget, or Other) and logs it.
  * **For Customers**:
    - **[ ORDER ]**: Automatically opens the standard Odoo Sales Order/Quotation form with pre-filled customer context. The new Sales Order is linked back to the visit.
    - **[ REVISIT ]**: Prompts to choose a date and automatically schedules the next visit.
    - **[ ISSUE ]**: Logs customer complaints, feedback, or issues and flags the manager.

2. MANAGER & SUPERVISOR ANALYTICS DASHBOARDS
-------------------------------------------
An interactive tabbed dashboard tailored for management:

- **Assignments Dashboard**: Counters and metrics for Assigned, Pending, Completed, Missed, and Revisit Schedule visits with quick scheduling lists.
- **Live Route Map**:
  * Interactive Leaflet map displaying Customer markers (blue), Lead markers (yellow), Revisit markers (orange), and Successful check-ins (green).
  * Renders live rep positions and route trail dots connecting consecutive check-ins to map daily coverage.
- **Performance Analytics**:
  * Tracks total completed visits, converted leads, generated revenue, and Conversion Rate.
  * **GPS Compliance %**: A computed compliance rating representing the percentage of successful check-ins out of total check-in attempts (successful + blocked attempts).
- **Customer Coverage**:
  * Displays a list of customers who haven't been visited in 30, 60, or 90+ days to prevent client neglect.

3. IMMUTABILITY & AUDITING
---------------------------
- **Sales Visit Audit Log**:
  * Captures every check-in, checkout, coordinate locking, reassignment, and blocked cheat attempt.
  * Strict database-level rules completely prevent write or unlink (delete) operations on audit logs, making them entirely tamper-proof.
- **Automated Sweep Cron**:
  * Runs automatically every night at midnight to check for uncompleted past-due visits and marks them as "Missed".
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
