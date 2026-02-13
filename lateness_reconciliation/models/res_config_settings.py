from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    lateness_annual_leave_type_id = fields.Many2one(
        related="company_id.lateness_annual_leave_type_id",
        readonly=False,
    )
