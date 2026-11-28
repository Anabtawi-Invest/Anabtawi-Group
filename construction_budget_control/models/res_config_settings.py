from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    construction_gm_threshold = fields.Monetary(
        related="company_id.construction_gm_threshold",
        readonly=False,
        string="General Manager Approval Threshold",
    )
    construction_chairman_threshold = fields.Monetary(
        related="company_id.construction_chairman_threshold",
        readonly=False,
        string="Chairman Approval Threshold",
    )
