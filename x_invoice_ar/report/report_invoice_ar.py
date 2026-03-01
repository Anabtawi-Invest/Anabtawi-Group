from odoo import models

class ReportInvoiceArabic(models.AbstractModel):
    _name = "report.x_invoice_ar.invoice_ar"
    _inherit = "report.account.report_invoice"
    _description = "Arabic Invoice Report"
