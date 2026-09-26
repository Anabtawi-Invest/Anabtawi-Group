# -*- coding: utf-8 -*-
{
    'name': 'Retail Labor Cost Report',
    'version': '19.0.1.0.0',
    'summary': 'Retail branches sales profit, labor cost by attendance days, and approved/unapproved overtime report',
    'description': """
Retail Labor Cost & Sales Profit Report
======================================
- Designed for Retail branches under the Retail department.
- Column 1: Branch Sales / Profits (integrated with POS Reporting Dashboard logic).
- Column 2: Total Branch Labor Cost (Attendance Days * hourly_wage * 8.0 hrs/day for all branch employees).
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
