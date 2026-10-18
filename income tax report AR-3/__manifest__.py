# -*- coding: utf-8 -*-
{
    "name": "Income Tax Report (AR/3) - شهادة ضريبة الدخل والرواتب",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Payroll",
    "summary": "Jordanian Income Tax Certificate AR/3 for Employees (شهادة مجموع الرواتب والأجور والضريبة المقتطعة - نموذج ار/3)",
    "description": """
Income Tax Report AR/3 (Jordan ISTD Official Form)
==================================================
This module provides the official Jordanian Income and Sales Tax Department (ISTD)
withholding tax certificate for employees (شهادة مجموع الرواتب والأجور والضريبة المقتطعة - نموذج QP 177-F3).

Key Features:
-------------
* Adds an 'Income TAX report (AR/3)' option under Employees > Reporting menu.
* Adds a direct button and dedicated tab on the Employee profile.
* Interactive Wizard to select employee, tax year, and preview/adjust earnings and tax values.
* Automatically fetches and aggregates Gross Earnings and Income Tax (INCOME_TAX) from payslips.
* Accurately splits amounts into Jordanian Dinars and Fills (دينار وفلس) with numbers on the right.
* Formatted identical to the official ISTD government template with Coat of Arms logo.
* Formatted to gracefully fill the full A4 portrait page.
* Ready for one-click PDF generation via QWeb / wkhtmltopdf.
    """,
    "author": "Anabtawi Group / Nabil",
    "license": "LGPL-3",
    "depends": ["base", "hr", "hr_payroll"],
    "data": [
        "security/ir.model.access.csv",
        "report/report_paperformat.xml",
        "report/report_income_tax_ar3.xml",
        "views/income_tax_report_wizard_views.xml",
        "views/hr_employee_views.xml",
        "views/income_tax_menu_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
