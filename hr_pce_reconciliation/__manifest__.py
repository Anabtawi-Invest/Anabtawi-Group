# -*- coding: utf-8 -*-
{
    "name": "PCE Reconciliation (Button + Smart Review) - Odoo 19 Enterprise Safe",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Payroll",
    "summary": "Separate reconciliation button: OT unpaid bank, lateness offsets OT->Annual->Salary input. Smart Review screen with badges on Payrun.",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": ["hr_payroll", "hr_holidays", "hr_work_entry"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/hr_payslip_views.xml",
        "views/hr_payslip_run_views.xml",
        "views/hr_pce_review_views.xml",
        "views/hr_employee_views.xml"
    ],
    "installable": True,
    "application": False
}
