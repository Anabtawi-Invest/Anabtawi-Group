# -*- coding: utf-8 -*-
{
    'name': "SW - check in",
    'summary': "",
    'description': """
    """,
    'category': 'Portal',
    'author': "enbtawi",
    'version': '1.4',
    'depends': [
        'base', 'hr', 'hr_payroll', 'base_portal', 'hr_holidays',
        'resource', 'portal', 'hr_attendance',
        'hr_attendance_overtime_approval_bridge',
    ],
    'data': [
        'views/res_users_portal_employee.xml',
        'views/hr_employee_user_link.xml',
        'views/hr_employee_attendance_location.xml',
        'views/hr_work_location_geofence_views.xml',
        'views/portal_check_in_templates.xml',
    ],


    'license': "Other proprietary",
}
