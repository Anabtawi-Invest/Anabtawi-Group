# -*- coding: utf-8 -*-
{
    'name': 'Employees Cost Center',
    'version': '19.0.1.0.0',
    'summary': 'Employees Cost Center calculation & Excel export based on hourly wage and attendance days',
    'description': """
Employees Cost Center Report
============================
- Calculates employee monthly cost to company based on:
  * Employee Technical Field: Hourly Wage (hourly_wage)
  * Daily Rate (hourly_wage * 8.0 hours/day)
  * Actual Attendance Days from Payslip Worked Days (Attendance line)
- Formula: Monthly Cost = Attendance Days * (Hourly Wage * 8.0)
- In-wizard interactive live preview before exporting to Excel.
- Multi-filter by Company, Departments, Employees, and Pay Run / Period.
- Formatted signed XLSX export with automated formulas and KPI summaries.
- Accessible directly from Payroll -> Reporting menu.
    """,
    'category': 'Human Resources/Payroll',
    'author': 'Anabtawi Group',
    'license': 'LGPL-3',
    'depends': [
        'hr_payroll',
    ],
    'external_dependencies': {
        'python': ['xlsxwriter'],
    },
    'data': [
        'security/ir.model.access.csv',
        'views/cost_center_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
