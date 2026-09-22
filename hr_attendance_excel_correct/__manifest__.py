{
    "name": "HR Attendance Excel Correct",
    "summary": "Upload Excel to preview and batch-correct employee check-in / check-out times",
    "version": "19.0.1.1.1",
    "category": "Human Resources/Attendances",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "hr_attendance",
    ],
    "external_dependencies": {
        "python": ["openpyxl"],
    },
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/attendance_excel_correct_tracking_views.xml",
        "wizard/attendance_excel_correct_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
}
