{
    "name": "Anabtawi Tax Audit & Declaration Report",
    "summary": "Consolidated Tax Audit & Return Declaration Reports in Excel (.xlsx) and PDF",
    "version": "19.0.1.0.0",
    "category": "Accounting/Localizations",
    "author": "Anabtawi Sweets",
    "license": "LGPL-3",
    "depends": [
        "account",
        "point_of_sale",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/tax_audit_report_wizard_view.xml",
        "reports/reports.xml",
        "reports/tax_audit_pdf_report_template.xml",
    ],
    "installable": True,
    "application": False,
}
