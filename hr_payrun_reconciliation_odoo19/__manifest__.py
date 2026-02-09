{
    "name": "Pay Run Lateness Reconciliation",
    "version": "19.0.1.0.0",
    "category": "Payroll",
    "summary": "Reconcile lateness: OT bank -> Annual Leave -> Unpaid input",
    "depends": ["hr_payroll", "hr_work_entry", "hr_holidays"],
    "data": [
        "views/hr_payslip_run_views.xml",
        "views/lateness_reco_preview_wizard_view.xml",
    ],
    "installable": True,
    "application": False,
}
