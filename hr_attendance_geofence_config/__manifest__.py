# -*- coding: utf-8 -*-
{
    'name': "HR Attendance Geofence Config",
    'summary': "Attendance geofence settings by work location",
    'description': """
Provides work location geofence fields and attendance settings UI.
    """,
    'category': 'Human Resources/Attendances',
    'author':"Anabtawi",
    'version': '1.0',
    'depends': ['base', 'hr', 'hr_attendance'],
    'data': [
        'views/hr_attendance_geofence_views.xml',
    ],
    'license': "Other proprietary",
}
