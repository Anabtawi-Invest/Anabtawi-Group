{
    "name": "Payroll Extra Hours Adjustment",
    "summary": "Manual payroll action to add employee extra hours balance",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Payroll",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "hr_payroll",
        "hr_holidays_attendance",
        "anabtawi_payroll_overtime",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/hr_payslip_views.xml",
    ],
    "installable": True,
    "application": False,
}
