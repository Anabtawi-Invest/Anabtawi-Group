from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    company_currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        string="Company Currency",
        readonly=True,
    )
    construction_gm_threshold = fields.Monetary(
        related="company_id.construction_gm_threshold",
        readonly=False,
        string="General Manager Approval Threshold",
        currency_field="company_currency_id",
    )
    construction_chairman_threshold = fields.Monetary(
        related="company_id.construction_chairman_threshold",
        readonly=False,
        string="Chairman Approval Threshold",
        currency_field="company_currency_id",
    )
