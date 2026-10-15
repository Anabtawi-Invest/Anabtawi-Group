# -*- coding: utf-8 -*-
{
    "name": "TIME OFF BALANCES",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Time Off",
    "summary": "Employee Time Off Balances Report and Ledger (Excel & PDF) - كشف رصيد وحركات الإجازات",
    "description": """
TIME OFF BALANCES REPORT
========================
This module generates an exact ledger and account statement for employee leave balances,
tracking allocations and leave deductions chronologically:
* Start date, End date
* Before Balance
* Days (+ / -)
* After Balance
* Credit (Checked / Unchecked)
* Description (e.g. Monthly Auto Credit, Added by TK, Subtractive Hours, Notes)
* Added By System (Checked / Unchecked)
* Added By TK (Checked / Unchecked)
* Posted (Checked / Unchecked)
* Total Days / Sum
* Dual Export: Excel (.xlsx) and PDF (QWeb).
* Menu location: Time Off > Reporting > TIME OFF BALANCES REPORT.
    """,
    "author": "Anabtawi Group / Nabil",
    "license": "LGPL-3",
    "depends": ["base", "hr", "hr_holidays"],
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
