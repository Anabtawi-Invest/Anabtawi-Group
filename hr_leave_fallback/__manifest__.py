{
    "name": "HR Leave Fallback",
    "version": "19.0.1.0.0",
    "summary": "Fallback leave requests to Sick, Annual, then Unpaid",
    "category": "Human Resources/Time Off",
    "author":"Anabtawi",
    "license": "LGPL-3",
    "depends": [
        "hr_holidays",
    ],
    "data": [
        "views/hr_leave_type_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "application": False,
}
