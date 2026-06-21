# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    visit_ids = fields.One2many(
        'sales.visit',
        'opportunity_id',
        string='Visits'
    )
    visit_count = fields.Integer(
        string='Visits Count',
        compute='_compute_visit_count'
    )

    @api.depends('visit_ids')
    def _compute_visit_count(self):
        for lead in self:
            lead.visit_count = len(lead.visit_ids)

    def action_view_visits(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("sales_visit_tracking.action_sales_visit")
        action['domain'] = [('opportunity_id', '=', self.id)]
        action['context'] = {
            'default_opportunity_id': self.id,
            'default_partner_id': self.partner_id.id,
            'default_user_id': self.user_id.id or self.env.user.id
        }
        return action
