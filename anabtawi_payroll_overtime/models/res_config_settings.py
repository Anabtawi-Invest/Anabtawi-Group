from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    overtime_hourly_amount = fields.Float(
        related="company_id.overtime_hourly_amount",
        readonly=False,
        string="Overtime Hourly Amount",
    )
