# -*- coding: utf-8 -*-
{
    "name": "HR Payroll Advanced (OT Bank + Lateness Reconcile)",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Payroll",
    "summary": "Reconcile lateness (OT -> Leave -> Salary), reconciliation badge, payroll control, and live OT bank balance.",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": ["hr_payroll", "hr_work_entry", "hr_holidays", "account"],
    "data": [
        "views/hr_payslip_views.xml",
        "views/hr_employee_views.xml",
    ],
    "installable": True,
    "application": False,
}
