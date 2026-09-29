from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    itr_receipt_company_id = fields.Many2one(
        'res.company',
        string='Source Company',
        config_parameter='internal_transfer_excel_report.receipt_company_id',
    )
    itr_receipt_vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor Company',
        domain="[('is_company', '=', True)]",
        config_parameter='internal_transfer_excel_report.receipt_vendor_id',
    )
    itr_receipt_location_id = fields.Many2one(
        'stock.location',
        string='Source Location',
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [itr_receipt_company_id, False])]",
        config_parameter='internal_transfer_excel_report.receipt_location_id',
    )
