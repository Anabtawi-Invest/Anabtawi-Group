# -*- coding: utf-8 -*-
{
    'name': 'Retail Labor Cost Report',
    'version': '19.0.1.0.2',
    'summary': 'Retail branches sales profit (POS shift window), labor cost by attendance days, and overtime report',
    'description': """
Retail Labor Cost & Sales Profit Report
======================================
- Designed for Retail branches under the Retail department.
- Column 1: Branch Sales / Profits (integrated with POS Reporting Dashboard store shift window 06:00 to 05:00 next day).
- Column 2: Total Branch Labor Cost (Attendance Days from Payslip * hourly_wage * 8.0 hrs/day for all branch employees).
- Column 3: Total Branch Overtime Hours (Approved OT vs. Unapproved OT vs. Total OT).
- Additional Insights: Net Contribution Margin (Sales - Labor Cost) & Labor Cost %.
- Accessible directly from Payroll -> Reporting menu.
- Interactive pop-up wizard with live in-form preview and signed XLSX export.
    """,
    'category': 'Human Resources/Payroll',
    'author': 'Anabtawi Group',
    'license': 'LGPL-3',
    'depends': [
        'hr_payroll',
        'point_of_sale',
        'hr_attendance',
    ],
    'external_dependencies': {
        'python': ['xlsxwriter'],
    },
    'data': [
        'security/ir.model.access.csv',
        'views/retail_labor_cost_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
