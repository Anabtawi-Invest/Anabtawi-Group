{
    "name": "HR Payroll Advanced (OT/Late Reconciliation)",
    "version": "19.0.1.0",
    "depends": ["hr_payroll", "hr_holidays"],
    "data": [
        "views/hr_payslip_views.xml",
        "views/hr_employee_views.xml",
        "data/server_actions.xml",
    ],
    "installable": True,
    "application": False,
}
