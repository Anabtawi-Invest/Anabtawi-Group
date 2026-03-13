from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    lateness_annual_leave_type_id = fields.Many2one(
        'hr.leave.type',
        string='Annual Leave Type for Lateness (Hours)',
        help='Leave type used to cover remaining lateness after consuming overtime buckets.',
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    annual_leave_type_id = fields.Many2one(
        related='company_id.lateness_annual_leave_type_id',
        readonly=False,
    )