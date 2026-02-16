# -*- coding: utf-8 -*-
{
    "name": "HR Payroll Reconciliation",
    "version": "19.0.1.0",
    "category": "Human Resources/Payroll",
    "summary": "Idempotent reconciliation: OT banked once, lateness deducted OT→Leave→Salary remainder. Buttons on Payslip & Payrun.",
    "author": "Anabtawi Group (Generated)",
    "license": "LGPL-3",
    "depends": ["hr_payroll", "hr_holidays"],
    "data": [
        "views/hr_employee_views.xml",
        "views/hr_payslip_views.xml",
        "views/hr_payslip_run_views.xml",
    ],
    "installable": True,
    "application": False,
}
