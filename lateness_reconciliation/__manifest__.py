
{
    "name": "Lateness Reconciliation",
    "version": "19.0.1.0.0",
    "category": "Payroll",
    "summary": "Enterprise Dashboard for Lateness + OT Bank + Remaining (Stable Odoo 19)",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": ["hr_payroll"],
    "data": [
        "views/hr_payslip_views.xml",
        "views/hr_payslip_run_views.xml",
        "data/mass_reconcile_action.xml"
    ],
    "installable": True,
    "application": False
}
