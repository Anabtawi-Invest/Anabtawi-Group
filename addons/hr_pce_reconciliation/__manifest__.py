{
    "name": "Payroll Reconciliation EngineLESS",
    "version": "19.6.0",
    "summary": "Automatic lateness reconciliation using OT Total + Annual Leave + Salary Inputs",
    "category": "Human Resources/Payroll",
    "author": "Anabtawi Group",
    "license": "OEEL-1",

    "depends": [
        "hr_payroll",
    ],

    "data": [
        "security/ir.model.access.csv",
        "views/menu.xml",
        "views/smart_review_views.xml",
    ],

    "installable": True,
    "application": False,
    "auto_install": False,
}
