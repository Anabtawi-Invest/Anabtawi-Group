{
    "name": "Attendance Overtime Approval Bridge",
    "version": "19.0.1.0.0",
    "summary": "Require approved Approval Requests before validating extra hours",
    "author": "Custom",
    "license": "LGPL-3",
    "depends": [
        "hr_attendance",
        "hr_attendance_weekly_overtime_eligibility",
        "approvals",
        "portal",
        "website",
    ],
    "data": [
        "data/ir_cron.xml",
        "views/approval_request_views.xml",
        "views/hr_attendance_views.xml",
        "views/portal_templates.xml",
    ],
    "installable": True,
    "application": False,
}

