{
    "name": "Anabtawi Salary Adjustments Excel Import",
    "summary": "Bulk create salary adjustments from an Excel template with a preview step",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Payroll",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "hr_payroll",
    ],
    "external_dependencies": {
        "python": ["openpyxl"],
    },
    "data": [
        "security/ir.model.access.csv",
        "wizard/salary_adjustment_import_wizard_views.xml",
        "views/hr_salary_attachment_views.xml",
    ],
    "installable": True,
    "application": False,
}
