# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ReportPosOrder(models.Model):
    _inherit = "report.pos.order"

    start_at = fields.Datetime(string="Session Start At", readonly=True)

    def _select(self):
        return super()._select() + ",ps.start_at AS start_at"

    def _group_by(self):
        return super()._group_by() + ",ps.start_at"