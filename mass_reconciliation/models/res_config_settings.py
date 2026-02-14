from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    annual_leave_type_id = fields.Many2one(
        'hr.leave.type',
        string='Annual Leave Type for Lateness (Hours)',
        help='Hour-based leave type used to cover remaining lateness after consuming OT buckets.',
        config_parameter='lateness_coverage.annual_leave_type_id',
    )