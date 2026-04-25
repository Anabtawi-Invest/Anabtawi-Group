{
    "name": "HR Attendance Weekly Overtime Eligibility",
    "version": "19.0.2.0.0",
    "summary": "Require minimum weekly worked hours before overtime approval",
    "author": "Custom",
    "license": "LGPL-3",
    "depends": [
        "hr_attendance",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "views/hr_attendance_views.xml",
    ],
    "installable": True,
    "application": False,
}
