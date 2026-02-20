from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    annual_leave_type_id = fields.Many2one(
        related='company_id.lateness_annual_leave_type_id',
        readonly=False,
    )