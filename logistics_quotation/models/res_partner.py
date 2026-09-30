# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _auto_init(self):
        # Auto-create missing columns in PostgreSQL table if module upgrade was not triggered
        cr = self.env.cr
        cr.execute("""
            ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS is_freight_forwarder BOOLEAN DEFAULT FALSE;
            ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS forwarder_approval_state VARCHAR DEFAULT 'draft';
            ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS forwarder_approved_by INTEGER;
            ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS forwarder_approved_date TIMESTAMP;
        """)
        return super()._auto_init()

    def _register_hook(self):
        res = super()._register_hook()
        try:
            self.env.cr.execute("""
                ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS is_freight_forwarder BOOLEAN DEFAULT FALSE;
                ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS forwarder_approval_state VARCHAR DEFAULT 'draft';
                ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS forwarder_approved_by INTEGER;
                ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS forwarder_approved_date TIMESTAMP;
            """)
        except Exception:
            pass
        return res

    is_freight_forwarder = fields.Boolean(
        string='Is Freight Forwarder',
        default=False,
        copy=False,
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
        copy=False,
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
