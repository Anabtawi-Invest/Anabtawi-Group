# -*- coding: utf-8 -*-

from odoo import api, models


class HrWorkEntryType(models.Model):
    _inherit = 'hr.work.entry.type'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('round_days', 'NO') != 'NO' and not vals.get('round_days_type'):
                vals['round_days_type'] = 'DOWN'
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get('round_days') in ('HALF', 'FULL') and not vals.get('round_days_type'):
            vals['round_days_type'] = 'DOWN'
        res = super().write(vals)
        bad_types = self.filtered(lambda t: t.round_days != 'NO' and not t.round_days_type)
        if bad_types:
            bad_types.sudo().write({'round_days_type': 'DOWN'})
        return res
