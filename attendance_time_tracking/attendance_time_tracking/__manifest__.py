{
    'name': 'Attendance Time Tracking',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Attendances',
    'summary': 'Enforce check-in windows, auto-checkout, and overtime-aware attendance control',
    'description': """
Attendance Time Tracking
========================
- Enforces check-in only within allowed working hours (work schedule or planning shift)
- Supports 30-minute early check-in tolerance
- Auto-checkout after 15 minutes past end of shift
- Overtime requests: if approved, extends allowed check-in window and delays auto-checkout
- Works for both schedule-based and planning-based employees
    """,
    'author': 'Custom Development',
    'depends': [
        'hr_attendance',
        'hr',
        'resource',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/ir_cron.xml',
        'views/overtime_request_views.xml',
        'views/attendance_config_views.xml',
        'views/hr_attendance_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
