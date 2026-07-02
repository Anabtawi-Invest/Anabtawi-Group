{
    "name": "Anabtawi Mobile API",
    "version": "19.0.1.2.0",
    "summary": "Secure mobile API for Anabtawi HR attendance, leave, and overtime",
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
