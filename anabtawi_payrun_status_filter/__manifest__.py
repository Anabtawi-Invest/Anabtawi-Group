# -*- coding: utf-8 -*-
{
    "name": "Payrun Employment Status Filter",
    "version": "19.0.1.1.0",
    "category": "Human Resources",
    "summary": "Terminated employee handling across Payroll, Time Off, Attendance, and POS",
    "description": """
Payrun & Employment Status Policy
=================================
* Excludes Suspended, Terminated, and On Leave employees from Pay Run batch payslips.
* When employee status (profile_employment_status) is set to 'Terminated':
    - Unlinks the related user account (user_id = False).
    - Keeps employee active in the database so they remain visible in Employees module.
    - Closes active contract version end date.
    - Hides terminated employees from Time Off new requests and allocations, while retaining full visibility of past leaves & balances.
    - Prevents attendance recording, kiosk check-in/out, and manual selection.
    - Excludes terminated employees from POS employee discount search (15% discount) and rejects any discount authorization.
    """,
    "author": "Anabtawi Group / Nabil",
    "license": "LGPL-3",
    "depends": [
        "base",
        "hr",
        "hr_payroll",
        "anabtawi_employee_profile",
        "hr_holidays",
        "hr_attendance",
        "point_of_sale",
        "pos_predefined_discounts",
        "employee_request",
    ],
    "data": [
        "views/hr_attendance_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
