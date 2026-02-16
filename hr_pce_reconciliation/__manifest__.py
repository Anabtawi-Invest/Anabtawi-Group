# -*- coding: utf-8 -*-
{
    "name": "Payroll Control Engine - Reconciliation",
    "version": "19.0.1.0.1",
    "category": "Human Resources/Payroll",
    "summary": "Reconcile lateness with priority OT -> Annual Leave -> Salary, and sync Payroll/Time Off/Attendance/Accounting.",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": ["hr_payroll", "hr_holidays", "hr_work_entry"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/hr_payslip_views.xml",
        "views/hr_payslip_run_views.xml",
        "views/hr_work_entry_views.xml",
        "data/input_types.xml"
    ],
    "installable": True,
    "application": False
}
