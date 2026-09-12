{
    'name': 'Reconciled Report',
    'version': '19.0.1.0.0',
    'summary': 'Payroll reconciliation report with signed, colour-coded Excel export',
    'category': 'Human Resources/Payroll',
    'license': 'LGPL-3',
    'depends': ['hr_payroll', 'factory_attendance_payroll'],
    'external_dependencies': {'python': ['xlsxwriter']},
    'data': ['security/ir.model.access.csv', 'views/report_wizard_views.xml'],
    'installable': True,
    'application': False,
}
