# -*- coding: utf-8 -*-
import calendar
from datetime import timedelta

from odoo import fields, models
from odoo.tools.float_utils import float_round


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    first_month_prorated = fields.Boolean(
        string='First month prorated',
        default=False,
        copy=False,
        readonly=True,
        help='Set once the prorated first-month accrual was applied, so it is never applied twice.',
    )

    @staticmethod
    def _first_month_factor(ref_date):
        """Eligible calendar days / days in month, joining day included."""
        days_in_month = calendar.monthrange(ref_date.year, ref_date.month)[1]
        return (days_in_month - ref_date.day + 1) / days_in_month

    def _is_first_month_proration_due(self, level, period_start, period_end):
        self.ensure_one()
        plan = self.accrual_plan_id
        if not plan.prorate_first_month or self.first_month_prorated:
            return False
        if level.frequency != 'monthly' or plan.is_based_on_worked_time:
            return False
        if self.number_of_days or self.yearly_accrued_amount:
            return False
        ref_date = self._get_accrual_reference_date()
        if not ref_date or ref_date.day == 1:
            return False
        # Only the period containing the joining date, never a backdated one.
        return period_start <= ref_date <= period_end

    def _get_contract_end_date(self):
        """Last day of employment, or False while any contract is open-ended."""
        self.ensure_one()
        periods = self.employee_id.sudo()._get_all_contract_dates()
        if not periods or any(not date_to for _date_from, date_to in periods):
            return False
        return max(date_to for _date_from, date_to in periods)

    def _get_accrual_proration(self, level, period_start, period_end):
        """Return (factor, is_first_month) or None for a standard accrual.

        The accrual month is the month of the last day of the period.
        First month: joining day counts. Leaving month: leaving day counts.
        Months after the contract end accrue nothing.
        """
        self.ensure_one()
        plan = self.accrual_plan_id
        first_due = self._is_first_month_proration_due(level, period_start, period_end)
        contract_end = False
        if plan.prorate_last_month and level.frequency == 'monthly' and not plan.is_based_on_worked_time:
            contract_end = self._get_contract_end_date()
        if not first_due and not contract_end:
            return None

        month_date = self._get_accrual_reference_date() if first_due else period_end - timedelta(days=1)
        days_in_month = calendar.monthrange(month_date.year, month_date.month)[1]
        first_day = month_date.day if first_due else 1
        last_day = days_in_month
        if contract_end:
            if (contract_end.year, contract_end.month) < (month_date.year, month_date.month):
                return 0.0, first_due
            if (contract_end.year, contract_end.month) == (month_date.year, month_date.month):
                last_day = contract_end.day
        if first_day == 1 and last_day == days_in_month:
            return None
        return max(0, last_day - first_day + 1) / days_in_month, first_due

    def _add_days_to_allocation(self, current_level, current_level_maximum_leave, leaves_taken, period_start, period_end):
        proration = self._get_accrual_proration(current_level, period_start, period_end)
        if proration is None:
            return super()._add_days_to_allocation(
                current_level, current_level_maximum_leave, leaves_taken, period_start, period_end)
        factor, is_first_month = proration

        days_to_add = current_level.added_value
        if current_level.added_value_type == 'hour':
            days_to_add = days_to_add / self.employee_id._get_hours_per_day(self.date_from)
        days_to_add = float_round(days_to_add * factor, precision_digits=4)

        # Same caps as core, so the annual limit is enforced on the prorated amount.
        if current_level.cap_accrued_time_yearly:
            maximum_leave_yearly = current_level.maximum_leave_yearly
            if current_level.added_value_type == 'hour':
                maximum_leave_yearly = maximum_leave_yearly / self.employee_id._get_hours_per_day(self.nextcall or self.date_from)
            days_to_add = min(days_to_add, maximum_leave_yearly - self.yearly_accrued_amount)
        if current_level.cap_accrued_time:
            days_to_add = min(days_to_add, leaves_taken + current_level_maximum_leave - self.number_of_days)

        self.number_of_days += days_to_add
        self.yearly_accrued_amount += days_to_add
        if is_first_month:
            self.first_month_prorated = True
