{
    "name": "Anabtawi Employee App API",
    "version": "19.0.1.3.0",
    "summary": "Secure Employee App API for attendance, leave, overtime, and single-device restriction",
    "category": "Human Resources",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "base",
        "hr",
        "web",
        "portal_check_in",
        "portal_leaves",
        "hr_attendance_overtime_approval_bridge",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/mobile_device_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
