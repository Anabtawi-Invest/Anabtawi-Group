{
    "name": "Daily Leave to Annual Conversion",
    "version": "19.0.1.0.0",
    "summary": "Convert every 8 hours of a configured daily leave type into 1 annual leave day",
    "category": "Human Resources/Time Off",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "hr",
        "hr_holidays",
    ],
    "data": [
        "views/res_config_settings_views.xml",
        "views/hr_employee_views.xml",
    ],
    "installable": True,
    "application": False,
}
