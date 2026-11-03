# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PfrAllocRateWizard(models.TransientModel):
    _name = 'pfr.alloc.rate.wizard'
    _description = 'Repair Weighted Extra Hours / PTO Allocations'

    date_from = fields.Date(string="Period From", required=True)
    date_to = fields.Date(string="Period To", required=True)
    batch_size = fields.Integer(
        string="Payslips per step", default=25, required=True,
        help="How many payslips are repaired in one background step.")
    payslip_count = fields.Integer(compute='_compute_payslip_count')

    @api.depends('date_from', 'date_to')
    def _compute_payslip_count(self):
        Payslip = self.env['hr.payslip'].sudo()
        for wiz in self:
            wiz.payslip_count = Payslip.search_count(wiz._slip_domain()) if wiz.date_from and wiz.date_to else 0

    def _slip_domain(self):
        self.ensure_one()
        # Confirmed payslips only: no draft / cancel. Covers Odoo 19 validated/paid and legacy done.
        states = ['validated', 'paid', 'done']
        return [
            ('date_from', '>=', self.date_from),
            ('date_from', '<=', self.date_to),
            ('state', 'in', states),
            ('employee_id', '!=', False),
        ]

    def action_start(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError(_("Period To is before Period From."))
        if self.batch_size < 1:
            raise UserError(_("Payslips per step must be at least 1."))
        running = self.env['pfr.alloc.rate.batch'].search([('state', '=', 'running')], limit=1)
        if running:
            raise UserError(
                _("A repair is already running (%s). Wait for it to finish or cancel it.") % running.name)
        slips = self.env['hr.payslip'].sudo().search(self._slip_domain(), order='date_from, id')
        if not slips:
            raise UserError(_("No confirmed payslips found for this period."))
        batch = self.env['pfr.alloc.rate.batch'].create({
            'name': _("Allocation rates %s to %s") % (self.date_from, self.date_to),
            'date_from': self.date_from,
            'date_to': self.date_to,
            'batch_size': self.batch_size,
            'line_ids': [(0, 0, {'payslip_id': slip.id, 'state': 'pending'}) for slip in slips],
        })
        self.env.ref('payroll_fix_recon_alloc_rate.ir_cron_pfr_alloc_rate').sudo()._trigger()
        return batch.action_refresh()
