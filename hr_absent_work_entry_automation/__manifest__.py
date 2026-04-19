# -*- coding: utf-8 -*-
{
    "name": "HR Absent Work Entry Automation",
    "version": "19.0.1.0.0",
    "summary": "Auto-create absent work entries when no check in exists",
    "category": "Human Resources",
    "author":"Anabtawi",
    "license": "LGPL-3",
    "depends": [
        "hr_attendance",
        "hr_work_entry",
    ],
    "data": [
        "data/work_entry_type_data.xml",
        "data/ir_cron_data.xml",
    ],
    "installable": True,
    "application": False,
}
