# -*- coding: utf-8 -*-
{
    "name": "Payrun Employment Status Filter",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Payroll",
    "summary": "Excludes Suspended, Terminated, and On Leave employees from Pay Run",
    "description": """
Payrun Employment Status Filter
===============================
This module automatically excludes employees from Pay Run batch payslip generation if their
Employment Status (profile_employment_status) is set to:
* Suspended
* Terminated
* On Leave

Employees with status Active or not set will continue to be processed normally.
    """,
    "author": "Anabtawi Group / Nabil",
    "license": "LGPL-3",
    "depends": ["base", "hr", "hr_payroll", "anabtawi_employee_profile"],
    "data": [],
    "installable": True,
    "application": False,
    "auto_install": False,
}
