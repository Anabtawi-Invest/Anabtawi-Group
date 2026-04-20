# -*- coding: utf-8 -*-
{
    "name": "ZK Attendance Bridge",
    "version": "19.0.1.0.0",
    "category": "Human Resources",
    "summary": "Receive biometric attendance from an external bridge agent",
    "description": "Odoo.sh-safe ZK attendance receiver that imports punches sent by a local bridge agent.",
    "author": "Anabtawi Group",
    "website": "https://www.odoo.com",
    "depends": ["hr_attendance"],
    "data": [
        "security/ir.model.access.csv",
        "views/biometric_device_bridge_views.xml",
        "views/bridge_attendance_log_views.xml",
        "views/hr_employee_views.xml",
        "views/menus.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": True,
}
