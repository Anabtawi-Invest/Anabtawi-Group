# -*- coding: utf-8 -*-
{
    "name": "Payroll Pay Run Reconciliation (Hours)",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Payroll",
    "summary": "One-click pay run reconciliation: consume OT hours, annual leave hours, and create lateness inputs (hours only).",
    "author": "Custom",
    "license": "LGPL-3",
    "depends": [
        "hr",
        "hr_payroll",
        "hr_work_entry",
        "hr_attendance",
        "hr_holidays",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/hr_payrun_reconciliation_views.xml",
        "views/hr_payslip_run_views.xml",
        "views/res_config_settings_views.xml",
        "data/hr_payslip_input_types.xml",
    ],
    "installable": True,
    "application": False,
}
