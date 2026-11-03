# -*- coding: utf-8 -*-
"""Background batches that re-apply weighted Extra Hours / PTO allocations."""
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

_RUN_CTX = dict(
    tracking_disable=True, mail_notrack=True, mail_create_nolog=True,
    mail_activity_automation_skip=True,
)


class PfrAllocRateBatch(models.Model):
    _name = 'pfr.alloc.rate.batch'
    _description = 'PFR Allocation Rate Batch'
    _order = 'id desc'

    name = fields.Char(required=True)
    date_from = fields.Date(required=True, string="Period From")
    date_to = fields.Date(required=True, string="Period To")
    batch_size = fields.Integer(
        default=25, required=True,
        help="Payslips processed in one background step.")
    state = fields.Selection([
        ('running', 'Running'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='running', required=True, index=True)
    line_ids = fields.One2many('pfr.alloc.rate.line', 'batch_id', string="Log", readonly=True)
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
        return self._open_lines([('state', '=', 'pending')], _("Pending"))

    def action_view_skipped(self):
        return self._open_lines([('state', '=', 'skipped')], _("Skipped"))

    def _open_lines(self, extra_domain, name):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'pfr.alloc.rate.line',
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
            try:
                with self.env.cr.savepoint():
                    result, note = slip._pfr_alloc_rate_repair_allocations()
            except Exception as exc:
                if self._connection_lost(exc):
                    raise
                _logger.exception("[pfr_alloc_rate] slip %s failed", slip.id)
                line.write({'state': 'error', 'error': str(exc)})
                continue
            line.write({
                'state': result if result in ('done', 'skipped') else 'done',
                'error': note or False,
            })
        self.invalidate_recordset(['state'])
        if self.state != 'running':
            return
        if self.line_ids.filtered(lambda l: l.state == 'pending'):
            self.env.ref('payroll_fix_recon_alloc_rate.ir_cron_pfr_alloc_rate').sudo()._trigger()
        else:
            self.state = 'done'

    @staticmethod
    def _connection_lost(exc):
        message = str(exc).lower()
        return exc.__class__.__name__ in ('InterfaceError', 'OperationalError') \
            or 'cursor already closed' in message or 'ssl connection' in message

    @api.model
    def _cron_pfr_alloc_rate(self):
        batch = self.sudo().search([('state', '=', 'running')], order='id', limit=1)
        if batch:
            batch._process_next_chunk()


class PfrAllocRateLine(models.Model):
    _name = 'pfr.alloc.rate.line'
    _description = 'PFR Allocation Rate Log'
    _order = 'state, date_from, id'

    batch_id = fields.Many2one(
        'pfr.alloc.rate.batch', required=True, ondelete='cascade', index=True)
    payslip_id = fields.Many2one('hr.payslip', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='payslip_id.company_id', store=True)
    employee_id = fields.Many2one(related='payslip_id.employee_id', store=True)
    date_from = fields.Date(related='payslip_id.date_from', store=True)
    date_to = fields.Date(related='payslip_id.date_to', store=True)
    payslip_name = fields.Char(related='payslip_id.name', store=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('done', 'Done'),
        ('error', 'Error'),
        ('skipped', 'Skipped'),
    ], default='pending', required=True, index=True)
    error = fields.Text(string="Note / Error")
