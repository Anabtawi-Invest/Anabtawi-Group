# -*- coding: utf-8 -*-
from __future__ import annotations

from lxml import etree
from odoo import api, fields, models


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    lateness_hours = fields.Float(string='Lateness (hrs)', compute='_compute_mass_reconciliation_totals', store=False)
    overtime_hours = fields.Float(string='Overtime (hrs)', compute='_compute_mass_reconciliation_totals', store=False)
    remaining_lateness_hours = fields.Float(string='Remaining Lateness (hrs)', compute='_compute_mass_reconciliation_totals', store=False)

    @api.depends('slip_ids.worked_days_line_ids.number_of_hours',
                 'slip_ids.worked_days_line_ids.work_entry_type_id.code',
                 'slip_ids.input_line_ids.amount',
                 'slip_ids.input_line_ids.code')
    def _compute_mass_reconciliation_totals(self):
        for run in self:
            run.lateness_hours = sum(run.slip_ids.mapped('lateness_hours'))
            run.overtime_hours = sum(run.slip_ids.mapped('overtime_hours'))
            run.remaining_lateness_hours = sum(run.slip_ids.mapped('remaining_lateness_hours'))

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super().fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        if view_type != 'list':
            return res

        try:
            arch = etree.fromstring(res['arch'])
        except Exception:
            return res

        root = arch
        if root.tag not in ('list', 'tree'):
            return res

        existing = {n.get('name') for n in root.xpath(".//field") if n.get('name')}
        for fname in ('lateness_hours', 'overtime_hours', 'remaining_lateness_hours'):
            if fname not in existing and fname in self._fields:
                node = etree.Element('field', name=fname)
                node.set('optional', 'show')
                root.append(node)

        res['arch'] = etree.tostring(arch, encoding='unicode')
        return res
