{
    "name": "HR Career & Salary History",
    "version": "19.0.1.0.0",
    "summary": "Career path ledger on the employee form: promotions, transfers and wage changes",
    "category": "Human Resources",
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": ["hr", "mail"],
    "data": [
        "security/career_history_security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/hr_employee_career_history_views.xml",
        "views/hr_employee_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
