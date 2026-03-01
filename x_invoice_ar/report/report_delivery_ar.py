from odoo import models

class ReportDeliveryArabic(models.AbstractModel):
    _name = "report.x_invoice_ar.delivery_ar"
    _inherit = "report.stock.report_deliveryslip"
    _description = "Arabic Delivery Slip Report"
