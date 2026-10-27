# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    accrued_period_keys = fields.Char(
        string='Accrued periods', copy=False, readonly=True,
        help='Accrual periods already granted to this allocation. A period is granted at most once, '
             'however many times the accrual runs (cron, manual run, recompute).')

    def _add_days_to_allocation(self, current_level, current_level_maximum_leave, leaves_taken,
                                period_start, period_end):
        """Safeguard: grant any given period only once per allocation."""
        if not (isinstance(self.id, int) and self.id):
            return super()._add_days_to_allocation(
                current_level, current_level_maximum_leave, leaves_taken, period_start, period_end)
        self.ensure_one()
        key = '%s|%s' % (period_start, period_end)
        done = set(filter(None, (self.accrued_period_keys or '').split(',')))
        if key in done:
            _logger.info("[hr_allocation_contract_dates] allocation %s: period %s already accrued, skipped",
                         self.id, key)
            return None
        result = super()._add_days_to_allocation(
            current_level, current_level_maximum_leave, leaves_taken, period_start, period_end)
        done.add(key)
        self.sudo().with_context(tracking_disable=True, mail_notrack=True).write(
            {'accrued_period_keys': ','.join(sorted(done))})
        return result

    def _get_contract_period(self):
        """(first contract start, last day of employment or False while any contract is open-ended)."""
        self.ensure_one()
        try:
            periods = self.employee_id.sudo()._get_all_contract_dates()
        except Exception:
            periods = []
        periods = [p for p in (periods or []) if p and p[0]]
        if not periods:
            return False, False
        start = min(p[0] for p in periods)
        end = False if any(not p[1] for p in periods) else max(p[1] for p in periods)
        return start, end

    @api.onchange('employee_id', 'accrual_plan_id', 'allocation_type')
    def _onchange_contract_start_date(self):
        """Accrual allocation starts on the contract start date (editable afterwards)."""
        for allocation in self:
            if allocation.allocation_type != 'accrual' or not allocation.employee_id or allocation._origin.id:
                continue
            start, _end = allocation._get_contract_period()
            if start:
                allocation.date_from = start

    def _sync_contract_end_date(self):
        """End Date = termination / contract end, so core Odoo prorates the last period and stops accruing."""
        for allocation in self:
            if allocation.allocation_type != 'accrual' or not allocation.employee_id or not allocation.id:
                continue
            _start, end = allocation._get_contract_period()
            if end and allocation.date_to != end:
                try:
                    allocation.sudo().with_context(tracking_disable=True, mail_notrack=True).write({'date_to': end})
                except Exception:
                    _logger.exception("[hr_allocation_contract_dates] could not set End Date on allocation %s",
                                      allocation.id)

    def _process_accrual_plans(self, date_to=False, force_period=False, log=True):
        self._sync_contract_end_date()
        return super()._process_accrual_plans(date_to=date_to, force_period=force_period, log=log)
