{
    "name": "POS Employee Payroll Deduction",
    "summary": "Deduct employee POS debt from payslip",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Payroll",
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "hr_payroll",
        "account",
    ],
    "data": [
        "data/hr_payslip_input_type_data.xml",
        "views/hr_employee_views.xml",
        "views/pos_payment_method_views.xml",
        "views/hr_payslip_views.xml",
    ],
    "installable": True,
    "application": False,
}
