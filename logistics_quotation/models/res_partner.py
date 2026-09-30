# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_freight_forwarder = fields.Boolean(
        string='Is Freight Forwarder',
        default=False,
        help='Check if this vendor is a freight forwarder / logistics carrier.',
    )
    forwarder_approval_state = fields.Selection(
        [
            ('draft', 'Pending Accounting Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Forwarder Approval Status',
        default='draft',
        tracking=True,
        help='Accounting approval status required before broadcasting RFQs.',
    )
    forwarder_approved_by = fields.Many2one(
        'res.users',
        string='Forwarder Approved By',
        readonly=True,
        copy=False,
    )
    forwarder_approved_date = fields.Datetime(
        string='Forwarder Approval Date',
        readonly=True,
        copy=False,
    )

    def action_approve_forwarder(self):
        for partner in self:
            partner.write({
                'forwarder_approval_state': 'approved',
                'forwarder_approved_by': self.env.user.id,
                'forwarder_approved_date': fields.Datetime.now(),
            })
            partner.message_post(
                body=_("Freight forwarder approved by Accounting Manager %s.", self.env.user.name)
            )

    def action_reject_forwarder(self):
        for partner in self:
            partner.write({
                'forwarder_approval_state': 'rejected',
                'forwarder_approved_by': False,
                'forwarder_approved_date': False,
            })
            partner.message_post(
                body=_("Freight forwarder approval rejected by %s.", self.env.user.name)
            )
