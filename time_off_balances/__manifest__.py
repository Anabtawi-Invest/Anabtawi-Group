# -*- coding: utf-8 -*-
{
    "name": "TIME OFF BALANCES",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Time Off",
    "summary": "Employee Time Off Balances Report and Ledger (Excel & PDF)",
    "description": """
TIME OFF BALANCES REPORT
========================
This module generates an exact ledger and account statement for employee leave balances,
tracking allocations and leave deductions chronologically:
* Start date, End date
* Before Balance
* Days (+ / -)
* After Balance
* Description (e.g. Monthly Auto Credit, Subtractive Hours, Reconciled from system, Notes)
* Total Days / Sum
* Dual Export: Excel (.xlsx) and PDF (QWeb).
* Menu location: Time Off > Reporting > TIME OFF BALANCES REPORT.
    """,
    "author": "Anabtawi Group / Nabil",
    "license": "LGPL-3",
    "depends": ["base", "hr", "hr_holidays"],
    "external_dependencies": {
        "python": ["xlsxwriter"],
    },
    "data": [
        "security/ir.model.access.csv",
        "report/report_paperformat.xml",
        "report/report_time_off_balances.xml",
        "wizard/time_off_balances_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
