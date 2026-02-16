{
    "name": "PCE Payroll Reconciliation (Smart Engine)",
    "version": "19.4.0",
    "category": "Human Resources/Payroll",
    "summary": "OT bank + lateness reconciliation (OT -> Annual Leave -> Salary Input) with Payrun badge & buttons (Odoo 19 Enterprise safe).",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": ["hr_payroll", "hr_holidays"],
    "data": [
        "views/hr_payslip_views.xml",
        "views/hr_payslip_run_views.xml"
    ],
    "installable": True,
    "application": False
}
