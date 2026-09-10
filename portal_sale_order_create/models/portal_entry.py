# -*- coding: utf-8 -*-
from odoo import fields, models


class PortalEntry(models.Model):
    _inherit = "portal.entry"

    required_group_xmlid = fields.Char(
        string="Required Group XML ID",
        help="If set, the card is shown only to users in this group.",
    )

    def should_show_portal_card(self):
        self.ensure_one()
        if self.required_group_xmlid:
            return self.env.user.has_group(self.required_group_xmlid)
        return super().should_show_portal_card()
