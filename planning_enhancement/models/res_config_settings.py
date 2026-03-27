from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    planning_max_extra_hours = fields.Float(
        string="Maximum Extra Hours for Shift Assignment",
        related="company_id.planning_max_extra_hours",
        readonly=False,
    )
