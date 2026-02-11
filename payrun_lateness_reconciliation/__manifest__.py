{
    "name": "Pay Run Lateness Reconciliation",
    "version": "19.0.1.0.0",
    "category": "Payroll",
    "summary": "Deduct lateness via OT bank → AL → unpaid input",
    "depends": ["hr_payroll", "hr_holidays", "hr_work_entry"],
    "data": [
        "security/ir.model.access.csv",
        "views/hr_payslip_run_views.xml",
        "views/lateness_reco_preview_wizard_view.xml"
    ],
    "installable": True
}