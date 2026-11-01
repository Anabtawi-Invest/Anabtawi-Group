# -*- coding: utf-8 -*-
"""Recompute payslips in the background, one small batch per cron transaction."""
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_RUN_CTX = dict(
    tracking_disable=True, mail_notrack=True, mail_create_nolog=True,
    mail_activity_automation_skip=True,
)


class PfrPayslipRecomputeBatch(models.Model):
    _name = 'pfr.payslip.recompute.batch'
    _description = 'Payslip Recompute Batch'
    _order = 'id desc'

    name = fields.Char(required=True)
    date_from = fields.Date(required=True, string="Period From")
    date_to = fields.Date(required=True, string="Period To")
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    batch_size = fields.Integer(
        default=1, required=True,
        help="Payslips saved together. 1 keeps each step short so the database connection stays up.")
    state = fields.Selection([
        ('running', 'Running'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='running', required=True, index=True)
    payslip_ids = fields.Many2many(
        'hr.payslip', 'pfr_recompute_batch_slip_rel', 'batch_id', 'slip_id',
        string="Payslips", readonly=True)
    processed_slip_ids = fields.Many2many(
        'hr.payslip', 'pfr_recompute_batch_processed_rel', 'batch_id', 'slip_id',
        string="Processed", readonly=True)
    skipped_slip_ids = fields.Many2many(
        'hr.payslip', 'pfr_recompute_batch_skipped_rel', 'batch_id', 'slip_id',
        string="Skipped", readonly=True)
    payslip_count = fields.Integer(compute='_compute_progress')
    done_count = fields.Integer(compute='_compute_progress')
    skipped_count = fields.Integer(compute='_compute_progress')
    remaining_count = fields.Integer(compute='_compute_progress')
    log = fields.Text(readonly=True)

    @api.depends('payslip_ids', 'processed_slip_ids', 'skipped_slip_ids')
    def _compute_progress(self):
        for batch in self:
            total = len(batch.payslip_ids)
            skipped = len(batch.skipped_slip_ids)
            processed = len(batch.processed_slip_ids)
            batch.payslip_count = total
            batch.skipped_count = skipped
            batch.done_count = processed - skipped
            batch.remaining_count = total - processed

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

    def _mark(self, slip, skipped, message):
        vals = {'processed_slip_ids': [(4, slip.id)]}
        if skipped:
            vals['skipped_slip_ids'] = [(4, slip.id)]
        line = '%s | %s | %s | %s' % (
            slip.id, slip.employee_id.name or '', slip.date_from,
            (message or 'done').split('\n')[0],
        )
        vals['log'] = ((self.log or '') + line + '\n')[-20000:]
        self.write(vals)

    def _process_next_chunk(self):
        self.ensure_one()
        if self.state != 'running':
            return
        size = max(1, self.batch_size or 1)
        pending = (self.payslip_ids - self.processed_slip_ids).sorted(key=lambda s: (s.date_from, s.id))
        chunk = pending[:size]
        if not chunk:
            self.state = 'done'
            return
        Payslip = self.env['hr.payslip'].with_context(**_RUN_CTX).sudo()
        for slip in chunk:
            slip = Payslip.browse(slip.id)
            try:
                with self.env.cr.savepoint():
                    slip._pfr_recompute_paid_cycle()
            except Exception as exc:
                if self._connection_lost(exc):
                    raise
                _logger.exception("[payroll_fix_recon] recompute skipped slip %s", slip.id)
                self._mark(slip, True, str(exc))
                continue
            self._mark(slip, False, 'done')
        self.invalidate_recordset(['state'])
        if self.state != 'running':
            return
        if self.payslip_ids - self.processed_slip_ids:
            self.env.ref('payroll_fix_recon.ir_cron_pfr_recompute_payslips').sudo()._trigger()
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


class PfrPayslipRecomputeWizard(models.TransientModel):
    _name = 'pfr.payslip.recompute.wizard'
    _description = 'Recompute Payslips'

    date_from = fields.Date(string="Period From", required=True)
    date_to = fields.Date(string="Period To", required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    batch_size = fields.Integer(
        string="Payslips per step", default=1, required=True,
        help="How many payslips are saved in one background step. Leave this at 1.")
    payslip_count = fields.Integer(compute='_compute_payslip_count')

    @api.depends('date_from', 'date_to', 'company_id')
    def _compute_payslip_count(self):
        for wiz in self:
            wiz.payslip_count = self.env['hr.payslip'].search_count(wiz._slip_domain()) \
                if wiz.date_from and wiz.date_to and wiz.company_id else 0

    def _slip_domain(self):
        self.ensure_one()
        return [
            ('company_id', '=', self.company_id.id),
            ('date_from', '>=', self.date_from),
            ('date_from', '<=', self.date_to),
        ]

    def action_start(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError(_("Period To is before Period From."))
        if self.batch_size < 1:
            raise UserError(_("Payslips per step must be at least 1."))
        running = self.env['pfr.payslip.recompute.batch'].search([('state', '=', 'running')], limit=1)
        if running:
            raise UserError(_("A recompute is already running (%s). Wait for it to finish or cancel it.") % running.name)
        slips = self.env['hr.payslip'].search(self._slip_domain(), order='date_from, id')
        if not slips:
            raise UserError(_("No payslips start in this period."))
        batch = self.env['pfr.payslip.recompute.batch'].create({
            'name': _("Recompute %s to %s") % (self.date_from, self.date_to),
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company_id': self.company_id.id,
            'batch_size': self.batch_size,
            'payslip_ids': [(6, 0, slips.ids)],
        })
        self.env.ref('payroll_fix_recon.ir_cron_pfr_recompute_payslips').sudo()._trigger()
        return batch.action_refresh()
