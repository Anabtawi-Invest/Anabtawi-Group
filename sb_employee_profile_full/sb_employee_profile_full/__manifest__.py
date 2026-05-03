{
    "name": "SB Employee Profile (Full) - PDF + Missing Fields",
    "version": "19.0.1.0.0",
    "category": "Human Resources",
    "summary": "Adds missing employee profile fields/tables and prints Employee Profile PDF from employee form.",
    "author": "Softobia",
    "license": "LGPL-3",
    "depends": ["hr", "hr_contract"],
    "data": [
        "security/ir.model.access.csv",
        "views/hr_employee_profile_views.xml",
        "report/employee_profile_template.xml",
        "report/employee_profile_report.xml"
    ],
    "installable": True,
    "application": False
}