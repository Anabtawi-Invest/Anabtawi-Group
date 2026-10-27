# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

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
