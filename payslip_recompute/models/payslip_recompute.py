# -*- coding: utf-8 -*-
"""Recompute payslips in the background. Every payslip gets a log line."""
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_RUN_CTX = dict(
    tracking_disable=True, mail_notrack=True, mail_create_nolog=True,
    mail_activity_automation_skip=True,
)


class PayslipRecomputeBatch(models.Model):
    _name = 'payslip.recompute.batch'
    _description = 'Payslip Recompute Batch'
    _order = 'id desc'

    name = fields.Char(required=True)
    date_from = fields.Date(required=True, string="Period From")
    date_to = fields.Date(required=True, string="Period To")
    batch_size = fields.Integer(
        default=1, required=True,
        help="Payslips saved together. 1 keeps each step short so the database connection stays up.")
    state = fields.Selection([
        ('running', 'Running'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='running', required=True, index=True)
    line_ids = fields.One2many('payslip.recompute.line', 'batch_id', string="Log", readonly=True)
    payslip_count = fields.Integer(compute='_compute_progress')
    done_count = fields.Integer(compute='_compute_progress')
    error_count = fields.Integer(compute='_compute_progress')
    pending_count = fields.Integer(compute='_compute_progress')
    skipped_count = fields.Integer(compute='_compute_progress')

    @api.depends('line_ids.state')
    def _compute_progress(self):
        for batch in self:
            states = batch.line_ids.mapped('state')
            batch.payslip_count = len(states)
            batch.done_count = states.count('done')
            batch.error_count = states.count('error')
            batch.pending_count = states.count('pending')
            batch.skipped_count = states.count('skipped')

    def action_cancel(self):
        self.filtered(lambda b: b.state == 'running').write({'state': 'cancelled'})

    def action_refresh(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_errors(self):
        return self._open_lines([('state', '=', 'error')], _("Errors"))

    def action_view_pending(self):
        return self._open_lines([('state', '=', 'pending')], _("Not recomputed"))

    def action_view_skipped(self):
        return self._open_lines([('state', '=', 'skipped')], _("Skipped"))

    def _open_lines(self, extra_domain, name):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'payslip.recompute.line',
            'view_mode': 'list,form',
            'domain': [('batch_id', '=', self.id)] + extra_domain,
            'target': 'current',
        }

    def _process_next_chunk(self):
        self.ensure_one()
        if self.state != 'running':
            return
        size = max(1, self.batch_size or 1)
        lines = self.line_ids.filtered(lambda l: l.state == 'pending').sorted(
            key=lambda l: (l.date_from, l.id))[:size]
        if not lines:
            self.state = 'done'
            return
        Payslip = self.env['hr.payslip'].with_context(**_RUN_CTX).sudo()
        for line in lines:
            slip = Payslip.browse(line.payslip_id.id)
            employee = slip.employee_id.with_context(active_test=False)
            if employee and not employee.active:
                line.write({
                    'state': 'skipped',
                    'error': _("Employee is archived."),
                })
                continue
            try:
                with self.env.cr.savepoint():
                    slip._recompute_paid_cycle()
            except Exception as exc:
                if self._connection_lost(exc):
                    raise
                _logger.exception("[payslip_recompute] slip %s failed", slip.id)
                line.write({'state': 'error', 'error': str(exc)})
                continue
            line.write({'state': 'done', 'error': False})
        self.invalidate_recordset(['state'])
        if self.state != 'running':
            return
        if self.line_ids.filtered(lambda l: l.state == 'pending'):
            self.env.ref('payslip_recompute.ir_cron_recompute_payslips').sudo()._trigger()
        else:
            self.state = 'done'

    @staticmethod
    def _connection_lost(exc):
        message = str(exc).lower()
        return exc.__class__.__name__ in ('InterfaceError', 'OperationalError') \
            or 'cursor already closed' in message or 'ssl connection' in message

    @api.model
    def _cron_recompute_payslips(self):
        batch = self.sudo().search([('state', '=', 'running')], order='id', limit=1)
        if batch:
            batch._process_next_chunk()


class PayslipRecomputeLine(models.Model):
    _name = 'payslip.recompute.line'
    _description = 'Payslip Recompute Log'
    _order = 'state, date_from, id'

    batch_id = fields.Many2one(
        'payslip.recompute.batch', required=True, ondelete='cascade', index=True)
    payslip_id = fields.Many2one('hr.payslip', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='payslip_id.company_id', store=True)
    employee_id = fields.Many2one(related='payslip_id.employee_id', store=True)
    date_from = fields.Date(related='payslip_id.date_from', store=True)
    date_to = fields.Date(related='payslip_id.date_to', store=True)
    payslip_name = fields.Char(related='payslip_id.name', store=True)
    state = fields.Selection([
        ('pending', 'Not recomputed'),
        ('done', 'Recomputed'),
        ('error', 'Error'),
        ('skipped', 'Skipped'),
    ], default='pending', required=True, index=True)
    error = fields.Text(string="Error")


class PayslipRecomputeWizard(models.TransientModel):
    _name = 'payslip.recompute.wizard'
    _description = 'Recompute Payslips'

    date_from = fields.Date(string="Period From", required=True)
    date_to = fields.Date(string="Period To", required=True)
    batch_size = fields.Integer(
        string="Payslips per step", default=1, required=True,
        help="How many payslips are saved in one background step. Leave this at 1.")
    skip_structure_ids = fields.Many2many(
        'hr.payroll.structure', string="Structures to skip",
        help="Payslips that use one of these salary structures are left out of the run.")
    payslip_count = fields.Integer(compute='_compute_payslip_count')

    @api.depends('date_from', 'date_to', 'skip_structure_ids')
    def _compute_payslip_count(self):
        for wiz in self:
            wiz.payslip_count = self.env['hr.payslip'].sudo().search_count(wiz._slip_domain()) \
                if wiz.date_from and wiz.date_to else 0

    def _slip_domain(self):
        self.ensure_one()
        domain = [
            ('date_from', '>=', self.date_from),
            ('date_from', '<=', self.date_to),
            ('employee_id.active', '=', True),
        ]
        if self.skip_structure_ids:
            domain.append(('struct_id', 'not in', self.skip_structure_ids.ids))
        return domain

    def action_start(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError(_("Period To is before Period From."))
        if self.batch_size < 1:
            raise UserError(_("Payslips per step must be at least 1."))
        running = self.env['payslip.recompute.batch'].search([('state', '=', 'running')], limit=1)
        if running:
            raise UserError(_("A recompute is already running (%s). Wait for it to finish or cancel it.") % running.name)
        slips = self.env['hr.payslip'].sudo().search(self._slip_domain(), order='date_from, id')
        if not slips:
            raise UserError(_("No payslips to recompute for this period."))
        batch = self.env['payslip.recompute.batch'].create({
            'name': _("Recompute %s to %s") % (self.date_from, self.date_to),
            'date_from': self.date_from,
            'date_to': self.date_to,
            'batch_size': self.batch_size,
            'line_ids': [(0, 0, {'payslip_id': slip.id, 'state': 'pending'}) for slip in slips],
        })
        self.env.ref('payslip_recompute.ir_cron_recompute_payslips').sudo()._trigger()
        return batch.action_refresh()
