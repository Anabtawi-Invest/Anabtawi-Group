from odoo import models

class ReportInvoiceArabic(models.AbstractModel):
    # لازم يطابق report_name الجديد: x_invoice_ar.x_invoice_ar_wrapper
    _name = "report.x_invoice_ar.x_invoice_ar_wrapper"
    # ورّث القيم من التقرير القياسي
    _inherit = "report.account.report_invoice"

class ReportInvoiceArabicWithPayments(models.AbstractModel):
    _name = "report.x_invoice_ar.x_invoice_ar_wrapper_with_payments"
    _inherit = "report.account.report_invoice_with_payments"
