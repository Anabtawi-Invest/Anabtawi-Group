# -*- coding: utf-8 -*-
"""Confirm / cancel lifecycle: settlements and Extra Hours allocations are only touched here,
never while a draft payslip is being computed."""
import logging
from collections import defaultdict
from datetime import datetime, time, timedelta

from odoo import models

from .pfr_settlement import recon_alloc_name

_logger = logging.getLogger(__name__)

PROFILE_FIELDS = ('total_overtime', 'total_extra_hours', 'extra_hours_balance', 'overtime_balance')
LEAVE_CTX = dict(
    mail_create_nolog=True, mail_notrack=True, tracking_disable=True, leave_skip_state_check=True,
    leave_skip_work_entries=True, no_work_entry=True, leave_skip_payslip_check=True,
    leave_skip_date_check=True, skip_payslip_validation=True, payslip_skip_leave_check=True,
    leave_fast_create=True,
)
ALLOC_CTX = dict(mail_create_nolog=True, mail_notrack=True, tracking_disable=True,
                 leave_fast_create=True, mail_activity_automation_skip=True)


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    def action_payslip_done(self):
        by_company = defaultdict(lambda: self.env['hr.payslip'])
        for slip in self:
            by_company[slip.company_id] |= slip
        res = True
        for slips in by_company.values():
            res = super(HrPayslip, slips).action_payslip_done()
        self.with_context(recon_synced_via_action=True)._pfr_sync_settlements()
        return res

    def action_payslip_draft(self):
        self._pfr_revert_settlements()
        return super().action_payslip_draft()

    def action_payslip_cancel(self):
        self._pfr_revert_settlements()
        return super().action_payslip_cancel()

    def unlink(self):
        self._pfr_revert_settlements()
        return super().unlink()

    def write(self, vals):
        if vals.get('state') == 'cancel' and not self.env.context.get('skip_reconcile_revert'):
            self.with_context(skip_reconcile_revert=True)._pfr_revert_settlements()
        going_done = vals.get('state') == 'done'
        already_done = set(self.filtered(lambda s: s.state == 'done').ids) if going_done else set()
        res = super().write(vals)
        if going_done and not self.env.context.get('recon_synced_via_action'):
            to_sync = self.filtered(lambda s: s.state == 'done' and s.id not in already_done)
            if to_sync:
                to_sync.with_context(recon_synced_via_action=True)._pfr_sync_settlements()
        return res

    def _pfr_set(self, vals):
        """Write bookkeeping fields without re-triggering the revert/sync hooks."""
        return self.with_context(skip_reconcile_revert=True, recon_synced_via_action=True).sudo().write(vals)

    # ------------------------------------------------------------------
    # Sync (on confirm)
    # ------------------------------------------------------------------
    def _pfr_sync_settlements(self):
        types = self.env['pfr.settlement'].leave_types(self[:1].company_id)
        for slip in self:
            if not slip.employee_id or not slip.date_to:
                continue
            slip._pfr_create_annual_settlement_leaves(types['annual'][:1])
            if types['extra'] and 'hr.leave.allocation' in self.env:
                slip._pfr_force_extra_hours(types['extra'][:1])
            balance = round(slip.remaining_extra_hours_balance or 0.0, 2)
            emp = slip.employee_id.sudo()
            for fname in PROFILE_FIELDS:
                if fname in emp._fields:
                    emp.write({fname: balance})

    def _pfr_create_annual_settlement_leaves(self, leave_type):
        """Step 2: consume Annual Leave, one validated leave per settled day."""
        self.ensure_one()
        hours = self.lateness_covered_by_annual_leave
        if hours <= 0.01 or not leave_type or 'hr.leave' not in self.env:
            return
        Leave = self.env['hr.leave'].sudo()
        Leave.search([('employee_id', '=', self.employee_id.id), ('holiday_status_id', '=', leave_type.id),
                      ('request_date_from', '>=', self.date_from), ('request_date_to', '<=', self.date_to),
                      ('name', 'ilike', 'Lateness Settlement')]).unlink()
        alloc = self.env['hr.leave.allocation'].sudo().search([
            ('employee_id', '=', self.employee_id.id), ('holiday_status_id', '=', leave_type.id),
            ('state', '=', 'validate')], order='date_to desc, id desc', limit=1)
        ctx_leave = Leave.with_context(employee_id=self.employee_id.id, **LEAVE_CTX)

        remaining, day = hours, self.date_from
        while remaining > 0.01 and day <= self.date_to:
            chunk = min(remaining, 8.0)
            start = datetime.combine(day, time(8, 0))
            vals = {
                'name': f"Lateness Settlement (Annual Leave) - {day.strftime('%d/%m/%Y')}"
                        + ('' if chunk >= 7.99 else f" {round(chunk, 2)}h"),
                'employee_id': self.employee_id.id, 'holiday_status_id': leave_type.id,
                'request_date_from': day, 'request_date_to': day,
                'date_from': start, 'date_to': start + timedelta(hours=9.0 if chunk >= 7.99 else chunk),
                'number_of_days': 1.0 if chunk >= 7.99 else round(chunk / 8.0, 4), 'state': 'validate',
            }
            if alloc and 'holiday_allocation_id' in Leave._fields:
                vals['holiday_allocation_id'] = alloc.id
            try:
                ctx_leave.create(vals).sudo().write({'state': 'validate'})
            except Exception:
                _logger.exception("[payroll_fix_recon] annual settlement leave failed slip=%s day=%s", self.id, day)
            remaining -= chunk
            day += timedelta(days=1)

    def _pfr_force_extra_hours(self, extra_type):
        """Make the Extra Hours time-off balance equal the slip's Remaining Extra Hours Balance."""
        self.ensure_one()
        Alloc = self.env['hr.leave.allocation'].sudo()
        settlement = self.env['pfr.settlement']
        name = recon_alloc_name(self)
        Alloc.search([('employee_id', '=', self.employee_id.id), ('holiday_status_id', '=', extra_type.id),
                      ('name', '=', name)]).write({'state': 'confirm'})
        Alloc.search([('employee_id', '=', self.employee_id.id), ('name', '=', name)]).unlink()
        self.env.flush_all()

        target = round(self.remaining_extra_hours_balance or 0.0, 2)
        current = round(sum(settlement.balance_hours([self.employee_id.id], extra_type.ids).values()), 2)
        gap = round(target - current, 2)
        if gap > 0.01:
            vals = {'name': name, 'employee_id': self.employee_id.id, 'holiday_status_id': extra_type.id,
                    'number_of_days': round(gap / 8.0, 4), 'date_from': self.date_from}
            for fname, val in (('holiday_type', 'employee'), ('allocation_type', 'regular')):
                if fname in Alloc._fields:
                    vals[fname] = val
            alloc = Alloc.with_context(employee_id=self.employee_id.id, **ALLOC_CTX).create(vals)
            self._pfr_validate_allocation(alloc)
            self._pfr_set({'extra_hours_allocated_days': vals['number_of_days']})
        else:
            self._pfr_set({'extra_hours_allocated_days': 0.0})
            if gap < -0.05:
                _logger.warning("[payroll_fix_recon] slip=%s Extra Hours balance exceeds target by %sh "
                                "(lateness consumed prior balance); allocations cannot go negative.",
                                self.id, abs(gap))

    def _pfr_validate_allocation(self, alloc):
        alloc = alloc.sudo()
        if alloc.state == 'validate':
            return alloc
        try:
            if hasattr(alloc, 'action_approve'):
                alloc.action_approve()
                alloc.invalidate_recordset()
                if alloc.state == 'validate1' and hasattr(alloc, '_action_validate'):
                    alloc._action_validate()
        except Exception:
            _logger.exception("[payroll_fix_recon] allocation %s approve failed, forcing state", alloc.id)
        if alloc.state != 'validate':
            alloc.with_context(tracking_disable=True, mail_notrack=True).write({'state': 'validate'})
        return alloc

    # ------------------------------------------------------------------
    # Revert (draft / cancel / unlink)
    # ------------------------------------------------------------------
    def _pfr_revert_settlements(self):
        Leave = self.env['hr.leave'].sudo() if 'hr.leave' in self.env else None
        Alloc = self.env['hr.leave.allocation'].sudo() if 'hr.leave.allocation' in self.env else None
        for slip in self:
            if not slip.employee_id or not slip.date_to:
                continue
            if not slip.is_reconciled and slip.state in ('draft', 'verify'):
                continue                                         # fast path: nothing was applied
            slip._pfr_set({'is_reconciled': False, 'extra_hours_allocated_days': 0.0})
            emp = slip.employee_id.sudo()
            for fname in PROFILE_FIELDS:
                if fname in emp._fields:
                    emp.write({fname: round(slip.total_extra_hours_available, 2)})
            if Leave:
                settled = Leave.search([
                    ('employee_id', '=', emp.id),
                    '|', ('name', 'ilike', 'Lateness Settlement'), ('name', 'ilike', 'Extra Hours Balance Sync'),
                    ('date_from', '<=', datetime.combine(slip.date_to, time.max)),
                    ('date_to', '>=', datetime.combine(slip.date_from, time.min))])
                settled.write({'state': 'draft'})
                settled.unlink()
            if Alloc:
                allocs = Alloc.search([('employee_id', '=', emp.id), ('name', '=', recon_alloc_name(slip))])
                allocs.write({'state': 'confirm'})
                allocs.unlink()
