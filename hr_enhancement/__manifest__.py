# -*- coding: utf-8 -*-
{
    "name": "HR Enhancement",
    "version": "19.0.1.1.0",
    "category": "Human Resources",
    "summary": "Time off dashboard extras and attendance card PDF",
    "depends": ["hr_holidays", "hr_attendance"],
    "data": [
        "security/ir.model.access.csv",
        "reports/attendance_card_report.xml",
        "reports/attendance_card_templates.xml",
        "views/attendance_card_wizard_views.xml",
    ],
    "installable": True,
    "license": "LGPL-3",
    "assets": {
        "web.assets_backend": [
            "hr_enhancement/static/src/dashboard/time_off_card_patch.js",
            "hr_enhancement/static/src/dashboard/time_off_card_patch.xml",
        ],
    },
}
