{
    "name": "Attendance Overtime Approval Bridge",
    "version": "19.0.1.3.0",
    "summary": "Extra hours stay locked until the employee's manager approves them",
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
        "security/ir.model.access.csv",
        "security/extra_hours_approval_security.xml",
        "data/ir_cron.xml",
        "views/approval_request_views.xml",
        "views/hr_attendance_views.xml",
        "views/extra_hours_approval_views.xml",
        "views/hr_employee_views.xml",
        "views/portal_templates.xml",
    ],
    "installable": True,
    "application": False,
}

