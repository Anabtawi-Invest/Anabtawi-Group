# -*- coding: utf-8 -*-

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class HrWorkEntryType(models.Model):
    _inherit = 'hr.work.entry.type'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('round_days', 'NO') != 'NO' and not vals.get('round_days_type'):
                _logger.warning(
                    "[factory_attendance_payroll] Auto-setting round_days_type=DOWN on create "
                    "for work entry type vals=%s",
                    vals,
                )
                vals['round_days_type'] = 'DOWN'
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get('round_days') in ('HALF', 'FULL') and not vals.get('round_days_type'):
            _logger.warning(
                "[factory_attendance_payroll] Auto-setting round_days_type=DOWN on write "
                "for work entry type ids=%s vals=%s",
                self.ids,
                vals,
            )
            vals['round_days_type'] = 'DOWN'
        res = super().write(vals)
        bad_types = self.filtered(lambda t: t.round_days != 'NO' and not t.round_days_type)
        if bad_types:
            _logger.warning(
                "[factory_attendance_payroll] Repairing work entry types after write: %s",
                [(t.id, t.name, t.code, t.round_days, t.round_days_type) for t in bad_types],
            )
            bad_types.sudo().write({'round_days_type': 'DOWN'})
        return res
