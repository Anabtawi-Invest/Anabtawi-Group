# -*- coding: utf-8 -*-
{
    "name": "Employee Document Expiry & HR Email",
    "version": "19.0.2.2.0",
    "category": "Human Resources",
    "summary": "Expiry dates beside HR documents, HR email when overdue; unique employee name / ID per company.",
    "license": "LGPL-3",
    # SIM / internet uploads come from Enterprise hr_payroll (used by e.g. l10n_be_hr_contract_salary).
    "depends": ["hr", "mail", "hr_payroll"],
    "data": [
        "data/document_expiry_cron.xml",
        "views/hr_employee_document_expiry_views.xml",
    ],
    "installable": True,
    "application": False,
}
