{
    "name": "HR Payroll Advanced (OT/Late Reconciliation)",
    "version": "19.0.2.0",
    "depends": ["hr_payroll", "hr_holidays"],
    "data": [
        "data/server_actions.xml",
        "views/hr_payslip_views.xml",
        "views/hr_employee_views.xml",
    ],
    "installable": True,
    "application": False,
}
