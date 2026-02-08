
{
    "name": "Pay Run Reconciliation",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Payroll",
    "summary": "Reconcile lateness in Pay Runs using OT, Annual Leave, then Salary Deduction (Hours)",
    "author": "YourCompany",
    "license": "LGPL-3",
    "depends": ["hr", "hr_payroll", "hr_attendance", "hr_work_entry", "hr_holidays"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/hr_payslip_run_view.xml",
        "views/hr_payrun_reconciliation_view.xml"
    ],
    "installable": True,
    "application": False
}
