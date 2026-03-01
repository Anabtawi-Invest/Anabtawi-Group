from odoo import models

class ReportInvoiceArabic(models.AbstractModel):
    _name = "report.x_invoice_ar.x_invoice_ar_wrapper"
    _inherit = "report.account.report_invoice"
