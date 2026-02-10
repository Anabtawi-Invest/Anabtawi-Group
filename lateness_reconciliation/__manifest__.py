{
    "name": "Lateness Reconciliation",
    "version": "2.0",
    "category": "Human Resources",
    "depends": [
        "hr_payroll",
        "hr_attendance",
        "planning",
        "hr_holidays"
    ],
    "data": [
        "views/hr_payslip_form_view.xml",
        "views/hr_payslip_list_view.xml",
        "data/lateness_cron.xml",
        "data/mass_reconcile_action.xml"
    ],
    "installable": True,
    "application": False
}
