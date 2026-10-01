from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    delivery_split_location_ids = fields.Many2many(
        related="company_id.delivery_split_location_ids",
        readonly=False,
    )
