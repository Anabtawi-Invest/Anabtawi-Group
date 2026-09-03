# -*- coding: utf-8 -*-
{
    "name": "HR & Payroll Executive Dashboard & Reporting",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Payroll",
    "summary": "Executive HR & Payroll Dashboard, Payrun Analysis, Overtime/Attendance Reconciliation & Bank Transfer Reporting",
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": [
        "hr",
        "hr_payroll",
        "hr_attendance",
        "hr_work_entry",
        "web",
    ],
    "data": [
        "security/security_groups.xml",
        "security/ir.model.access.csv",
        "wizard/hr_payroll_report_wizard_views.xml",
        "views/hr_payroll_dashboard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "anabtawi_hr_payroll_dashboard/static/src/scss/hr_payroll_dashboard.scss",
            "anabtawi_hr_payroll_dashboard/static/src/js/hr_payroll_dashboard.js",
            "anabtawi_hr_payroll_dashboard/static/src/xml/hr_payroll_dashboard.xml",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
