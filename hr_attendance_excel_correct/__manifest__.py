{
    "name": "HR Attendance Excel Correct",
    "summary": "Upload Excel to preview and batch-correct employee check-in / check-out times",
    "version": "19.0.1.0.0",
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
        "wizard/attendance_excel_correct_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
}
