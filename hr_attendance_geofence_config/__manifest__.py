# -*- coding: utf-8 -*-
{
    'name': "HR Attendance Geofence Config",
    'summary': "Company geofence settings for attendance validation",
    'description': """
Provides company geofence fields and attendance settings UI.
    """,
    'category': 'Human Resources/Attendances',
    'author': "enbtawi",
    'version': '1.0',
    'depends': ['base', 'hr_attendance'],
    'data': [
        'views/hr_attendance_geofence_views.xml',
    ],
    'license': "Other proprietary",
}
