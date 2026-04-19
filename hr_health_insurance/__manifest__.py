# -*- coding: utf-8 -*-
{
    'name': 'SW - Health Insurance',
    'version': '1.0',
    'category': 'Human Resources',
    'summary': 'Employee health insurance management.',
    "author":"Anabtawi",
    'description': """
      * This module helps track detailed health insurance policies for employees and their dependents, with dynamic computation of policy amounts based on:
         - Insurance Grades
         - Insurance Contracts
      * A table is added to the employee profile to utilize, among other things, the following:
          _ Name
          _ Relation
          _ Birthdate
          _ Grade
          _ Employee Contribution percentage (to deduct from policy amount on payroll)
          _ Manual Contribution ( to manage cases with manual fixed amounts that override the current contract amounts on the set insurance contract)
      * Payroll Integration –  A salary rule is added on salary structure creation to automatically deduct the applicable monthly amount when generating employee payslips.
      """,
    'depends': ['base', 'hr_payroll_account', 'hr', 'mail', 'base_payroll_account'],
    'license': "Other proprietary",
    'data': [
        "security/ir.model.access.csv",
        "security/rules.xml",
        "view/menu_view.xml",
        "view/health_insurance.xml",
        "view/hr_health_grade_view.xml",
        "view/hr_health_contract_view.xml",
        "view/res_config.xml"
    ],
}
