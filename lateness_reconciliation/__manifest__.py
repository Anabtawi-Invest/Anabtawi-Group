{
"name": "Lateness Reconciliation",
"version": "1.0",
"category": "Human Resources",
"depends": ["hr_payroll", "hr_attendance", "planning", "mail"],
"data": [
"data/salary_input_type.xml",
"views/hr_payslip_form_view.xml",
"views/hr_payslip_fields_view.xml",
"views/hr_payslip_list_view.xml",
"views/hr_employee_view.xml",
"data/lateness_cron.xml",
"data/mass_reconcile_action.xml"
],
"installable": True,
"application": False
}
