from odoo import fields, models

class ResCompany(models.Model):
    _inherit = 'res.company'

    lateness_annual_leave_type_id = fields.Many2one(
        'hr.leave.type',
        string='Annual Leave Type for Lateness (Hours)',
        help='Leave type used to cover remaining lateness after consuming overtime buckets.',
    )
    lateness_ot_source = fields.Selection(
        [
            ('overtime_this_month', 'Overtime for this month'),
            ('ot_balance', 'OT Balance (hrs)'),
        ],
        string='OT source for lateness & planning',
        default='overtime_this_month',
        help='Payslip lateness deduction and Planning "Available OT" use this source.',
    )
    lateness_work_entry_codes = fields.Char(
        string='Lateness work entry codes',
        default='LAT,LATE,Lateness,L',
        help='Comma-separated work entry type codes that count as lateness (e.g. LAT,LATE,L).',
    )
    ot_priority_codes = fields.Char(
        string='OT priority codes (order matters)',
        default='OTR,PHO,OTW',
        help='Comma-separated OT work entry type codes; first = highest priority (e.g. OTR,PHO,OTW).',
    )


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