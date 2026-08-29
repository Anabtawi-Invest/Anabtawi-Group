{
    "name": "Anabtawi Employee App API",
    "version": "19.0.1.6.0",
    "summary": "Secure Employee App API for attendance, leave, OTP, password change, and single-device portal restriction",
    "category": "Human Resources",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "base",
        "hr",
        "web",
        "employee_request",
        "portal_check_in",
        "portal_leaves",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_config_parameter_data.xml",
        "views/mobile_device_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
