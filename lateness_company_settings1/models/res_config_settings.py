from odoo import fields, models



class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    lateness_annual_leave_type_id = fields.Many2one(
        related='company_id.lateness_annual_leave_type_id',
        readonly=False,
    )

    lateness_ot_source = fields.Selection(
        selection=[
            ('overtime_this_month', 'Overtime for this month'),
            ('ot_balance', 'OT Balance (hrs)'),
        ],
        related='company_id.lateness_ot_source',
        readonly=False,
    )

    lateness_work_entry_codes = fields.Char(
        related='company_id.lateness_work_entry_codes',
        readonly=False,
    )

    ot_priority_codes = fields.Char(
        related='company_id.ot_priority_codes',
        readonly=False,
    )
    annual_leave_type_id = fields.Many2one(
        related='company_id.lateness_annual_leave_type_id',
        readonly=False,
    )