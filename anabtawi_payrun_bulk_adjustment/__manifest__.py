{
    "name": "Anabtawi Payrun Bulk Salary Adjustments & Partial Payments",
    "summary": "Import bulk partial salary payments and salary adjustments per Payrun via Excel upload",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Payroll",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "hr_payroll",
        "hr_employee_code",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/hr_payslip_input_type_data.xml",
        "wizard/hr_payslip_run_import_wizard_views.xml",
        "views/hr_payslip_run_views.xml",
    ],
    "installable": True,
    "application": True,
}
