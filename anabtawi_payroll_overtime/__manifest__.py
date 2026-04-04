{
    "name": "Anabtawi Payroll Overtime Management",
    "summary": "Pay overtime from payslip inputs and deduct extra hour balance",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Payroll",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "hr_payroll",
        "hr_attendance",
        "hr_holidays_attendance",
    ],
    "data": [
        "views/hr_payslip_views.xml",
        "views/hr_payslip_input_type_views.xml",
    ],
    "installable": True,
    "application": False,
}
