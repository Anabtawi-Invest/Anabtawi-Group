{
    "name": "Anabtawi Salary Adjustments Excel Import",
    "summary": "Bulk create salary adjustments from an Excel template in the background, with review and import logs",
    "version": "19.0.1.2.0",
    "category": "Human Resources/Payroll",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "hr_payroll",
        "mail",
    ],
    "external_dependencies": {
        "python": ["openpyxl"],
    },
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "data/ir_cron_data.xml",
        "wizard/salary_adjustment_import_wizard_views.xml",
        "views/hr_salary_attachment_views.xml",
        "views/salary_adjustment_import_log_views.xml",
    ],
    "installable": True,
    "application": False,
}
