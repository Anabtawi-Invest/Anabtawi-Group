# -*- coding: utf-8 -*-
{
    "name": "HR Enhancement",
    "version": "19.0.1.4.0",
    "category": "Human Resources",
    "summary": "Time off, attendance card PDF, regulated employee documents",
    "depends": ["hr", "hr_holidays", "hr_attendance", "mail", "hr_health_insurance"],
    "data": [
        "security/ir.model.access.csv",
        "data/hr_health_document_type_data.xml",
        "views/hr_employee_personal_views.xml",
        "data/employee_document_migrate.xml",
        "data/employee_document_cron.xml",
        "reports/attendance_card_report.xml",
        "reports/report_pdf_anabtawi_layout.xml",
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
