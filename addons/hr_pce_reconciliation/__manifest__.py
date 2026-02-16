{
    "name": "PCE Payroll Reconciliation (ULTRA FINAL)",
    "version": "19.5.0",
    "category": "Human Resources/Payroll",
    "summary": "OT bank tracking + lateness reconciliation (OT -> Annual Leave -> Salary Input) with Smart Review screen & Payrun badges (Odoo 19 Enterprise safe).",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": ["hr_payroll", "hr_holidays"],
    "data": [
        "security/ir.model.access.csv",
        "views/hr_payslip_views.xml",
        "views/hr_payslip_run_views.xml",
        "wizard/pce_review_wizard_views.xml"
    ],
    "installable": True,
    "application": True
}
