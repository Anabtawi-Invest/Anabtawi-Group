# Part of Odoo. See LICENSE file for full copyright and licensing details.

from dateutil.relativedelta import relativedelta

from odoo import fields, models, _
from odoo.tools import format_date
from odoo.tools.date_utils import get_timedelta
from odoo.tools.float_utils import float_round


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    last_accrual_calculation_log = fields.Html(
        string='Accrual calculation',
        readonly=True,
        help='Shows how the accrual was calculated (reference date, levels, each step). Updated when you change Start Date, Employee or Accrual Plan.',
    )

    def _get_accrual_reference_date(self):
        """
        Date used as reference for accrual plan level milestones (e.g. level start).
        When the plan is set to 'contract', uses the employee's contract start:
        - contract active at allocation start date, or
        - if no contract at allocation start (e.g. allocation backdated), the employee's
          earliest contract start date (first day of employment).
        Otherwise uses the allocation start date.
        """
        self.ensure_one()
        if not self.accrual_plan_id:
            return self.date_from
        if getattr(self.accrual_plan_id, 'milestone_reference', 'allocation') != 'contract':
            return self.date_from
        contract_start, _ = self.employee_id.sudo()._get_contract_dates(self.date_from)
        if contract_start:
            return contract_start
        # No contract at allocation start (e.g. allocation from 2019, employee hired 2021)
        # Use employee's earliest contract start so "After 4 years" = 4 years from first contract
        all_periods = self.employee_id.sudo()._get_all_contract_dates()
        if all_periods:
            earliest_start = min(p[0] for p in all_periods)
            return earliest_start
        return self.date_from

    def _get_current_accrual_plan_level_id(self, date, level_ids=False):
        """
        Override to use milestone reference date (allocation or contract start) instead of date_from.
        """
        self.ensure_one()
        if not self.accrual_plan_id.level_ids:
            return (False, False)
        if not level_ids:
            level_ids = self.accrual_plan_id.level_ids.sorted('sequence')
        current_level = False
        current_level_idx = -1
        ref_date = self._get_accrual_reference_date()
        for idx, level in enumerate(level_ids):
            if date > ref_date + get_timedelta(level.start_count, level.start_type):
                current_level = level
                current_level_idx = idx
        if current_level_idx <= 0 or self.accrual_plan_id.transition_mode == "immediately":
            return (current_level, current_level_idx)
        level_start_date = ref_date + get_timedelta(current_level.start_count, current_level.start_type)
        previous_level = level_ids[current_level_idx - 1]
        if current_level._get_next_date(level_start_date) < previous_level._get_next_date(level_start_date):
            return (previous_level, current_level_idx - 1)
        return (current_level, current_level_idx)

    def _process_accrual_plans(self, date_to=False, force_period=False, log=True):
        """
        Override to use milestone reference date for level boundaries (contract or allocation start).
        """
        date_to = date_to or fields.Date.today()
        already_accrued = {
            allocation.id: allocation.already_accrued
            or (allocation.number_of_days != 0 and allocation.accrual_plan_id.accrued_gain_time == 'start')
            for allocation in self
        }
        first_allocation = _(
            "This allocation have already ran once, any modification won't be effective to the days "
            "allocated to the employee. If you need to change the configuration of the allocation, "
            "delete and create a new one."
        )
        for allocation in self:
            expiration_date = False
            if allocation.allocation_type != 'accrual':
                continue
            level_ids = allocation.accrual_plan_id.level_ids.sorted('sequence')
            if not level_ids:
                continue
            first_level = level_ids[0]
            ref_date = allocation._get_accrual_reference_date()
            first_level_start_date = ref_date + get_timedelta(first_level.start_count, first_level.start_type)

            # Build calculation log (visible on form and optionally in chatter)
            log_parts = []
            if log:
                ref_source = 'allocation'
                if getattr(allocation.accrual_plan_id, 'milestone_reference', 'allocation') == 'contract':
                    contract_start, _contract_end = allocation.employee_id.sudo()._get_contract_dates(allocation.date_from)
                    ref_source = _('Employee contract start (%s)') % format_date(allocation.env, ref_date) if contract_start else _('Employee earliest contract start (%s)') % format_date(allocation.env, ref_date)
                else:
                    ref_source = _('Allocation start (%s)') % format_date(allocation.env, ref_date)
                level_lines = []
                for idx, lvl in enumerate(level_ids):
                    lvl_start = ref_date + get_timedelta(lvl.start_count, lvl.start_type)
                    level_lines.append(_('Level %s: from %s → %s %s/%s') % (
                        idx + 1,
                        format_date(allocation.env, lvl_start),
                        lvl.added_value,
                        lvl.added_value_type == 'day' and _('day(s)') or _('hour(s)'),
                        lvl.frequency,
                    ))
                log_html = _(
                    '<p><b>Accrual calculation</b></p>'
                    '<p>Reference date: <b>%s</b> (%s)</p>'
                    '<p>Levels:</p><ul>%s</ul>'
                    '<p>Run until: %s</p>'
                ) % (
                    format_date(allocation.env, ref_date),
                    ref_source,
                    ''.join('<li>%s</li>' % line for line in level_lines),
                    format_date(allocation.env, date_to),
                )
                log_parts.append(log_html)
                if allocation.id and isinstance(allocation.id, int) and allocation.id > 0:
                    allocation._message_log(body=log_html)

            if allocation.holiday_status_id.request_unit in ["day", "half_day"]:
                leaves_taken = allocation.leaves_taken
            else:
                leaves_taken = allocation.leaves_taken / allocation.employee_id._get_hours_per_day(allocation.date_from)
            allocation.already_accrued = already_accrued[allocation.id]
            if not allocation.nextcall:
                if date_to < first_level_start_date:
                    continue
                allocation.lastcall = max(allocation.lastcall, first_level_start_date)
                allocation.actual_lastcall = allocation.lastcall
                allocation.nextcall = first_level._get_next_date(allocation.lastcall)
                carryover_date = allocation._get_carryover_date(allocation.nextcall)
                allocation.nextcall = min(carryover_date, allocation.nextcall)
                if len(level_ids) > 1:
                    second_level_start_date = ref_date + get_timedelta(level_ids[1].start_count, level_ids[1].start_type)
                    allocation.nextcall = min(second_level_start_date, allocation.nextcall)
                if log and allocation.id and isinstance(allocation.id, int) and allocation.id > 0:
                    allocation._message_log(body=first_allocation)
            (current_level, current_level_idx) = (False, 0)
            current_level_maximum_leave = 0.0
            while allocation.nextcall <= date_to:
                (current_level, current_level_idx) = allocation._get_current_accrual_plan_level_id(allocation.nextcall)
                if not current_level:
                    break
                if current_level.cap_accrued_time:
                    if current_level.added_value_type == "day":
                        current_level_maximum_leave = current_level.maximum_leave
                    else:
                        current_level_maximum_leave = current_level.maximum_leave / allocation.employee_id._get_hours_per_day(allocation.date_from)
                nextcall = current_level._get_next_date(allocation.nextcall)
                period_start = current_level._get_previous_date(allocation.lastcall)
                period_end = current_level._get_next_date(allocation.lastcall)
                current_level_last_date = False
                if current_level_idx < (len(level_ids) - 1) and allocation.accrual_plan_id.transition_mode == 'immediately':
                    next_level = level_ids[current_level_idx + 1]
                    current_level_last_date = ref_date + get_timedelta(next_level.start_count, next_level.start_type)
                    if allocation.nextcall != current_level_last_date:
                        nextcall = min(nextcall, current_level_last_date)
                carryover_date = allocation._get_carryover_date(allocation.nextcall)
                if allocation.nextcall < carryover_date < nextcall:
                    nextcall = min(nextcall, carryover_date)

                if current_level.accrual_validity:
                    expiration_date = allocation.carried_over_days_expiration_date
                    if not expiration_date or allocation.nextcall > expiration_date or allocation.expiring_carryover_days == 0:
                        expiration_date = carryover_date + relativedelta(
                            **{current_level.accrual_validity_type + 's': current_level.accrual_validity_count}
                        )
                        allocation.carried_over_days_expiration_date = expiration_date
                    if allocation.nextcall < expiration_date < nextcall:
                        nextcall = expiration_date
                    if allocation.nextcall == expiration_date:
                        expiring_days = max(0, allocation.expiring_carryover_days - allocation.leaves_taken)
                        allocation.number_of_days = max(0, allocation.number_of_days - expiring_days)
                        allocation.expiring_carryover_days = 0

                is_accrual_date = allocation.nextcall == period_end or allocation.nextcall == current_level_last_date
                if not allocation.already_accrued and is_accrual_date and allocation.accrual_plan_id.accrued_gain_time == 'start':
                    days_before = allocation.number_of_days
                    allocation._add_days_to_allocation(current_level, current_level_maximum_leave, leaves_taken, period_start, period_end)
                    if log and allocation.number_of_days != days_before:
                        step_log = _(
                            'Accrued <b>%s</b> %s for period %s → %s (level: %s %s %s, %s %s/%s)'
                        ) % (
                            allocation.number_of_days - days_before,
                            allocation.holiday_status_id.request_unit in ["day", "half_day"] and _('days') or _('hours'),
                            format_date(allocation.env, period_start),
                            format_date(allocation.env, period_end),
                            current_level.start_count,
                            current_level.start_type,
                            _('from ref'),
                            current_level.added_value,
                            current_level.added_value_type == 'day' and _('day(s)') or _('hour(s)'),
                            current_level.frequency,
                        )
                        log_parts.append('<p>%s</p>' % step_log)
                        if allocation.id and isinstance(allocation.id, int) and allocation.id > 0:
                            allocation._message_log(body=step_log)

                if allocation.nextcall == carryover_date:
                    allocation.last_executed_carryover_date = carryover_date
                    if current_level.action_with_unused_accruals == 'lost' or current_level.carryover_options == 'limited':
                        allocated_days_left = allocation.number_of_days - leaves_taken
                        allocation_max_days = 0
                        if current_level.carryover_options == 'limited':
                            if current_level.added_value_type == 'day':
                                postpone_max_days = current_level.postpone_max_days
                            else:
                                postpone_max_days = current_level.postpone_max_days / allocation.employee_id._get_hours_per_day(allocation.date_from)
                            allocation_max_days = min(postpone_max_days, allocated_days_left)
                        allocation.number_of_days = min(allocation.number_of_days, allocation_max_days) + leaves_taken
                    allocation.expiring_carryover_days = allocation.number_of_days

                if not allocation.already_accrued and is_accrual_date and allocation.accrual_plan_id.accrued_gain_time == 'end':
                    days_before = allocation.number_of_days
                    allocation._add_days_to_allocation(current_level, current_level_maximum_leave, leaves_taken, period_start, period_end)
                    if log and allocation.number_of_days != days_before:
                        step_log = _(
                            'Accrued <b>%s</b> %s for period %s → %s (level: %s %s %s, %s %s/%s)'
                        ) % (
                            allocation.number_of_days - days_before,
                            allocation.holiday_status_id.request_unit in ["day", "half_day"] and _('days') or _('hours'),
                            format_date(allocation.env, period_start),
                            format_date(allocation.env, period_end),
                            current_level.start_count,
                            current_level.start_type,
                            _('from ref'),
                            current_level.added_value,
                            current_level.added_value_type == 'day' and _('day(s)') or _('hour(s)'),
                            current_level.frequency,
                        )
                        log_parts.append('<p>%s</p>' % step_log)
                        if allocation.id and isinstance(allocation.id, int) and allocation.id > 0:
                            allocation._message_log(body=step_log)

                if allocation.nextcall == carryover_date:
                    allocation.yearly_accrued_amount = 0

                if allocation.accrual_plan_id.accrued_gain_time == 'start' and allocation.last_executed_carryover_date:
                    last_carryover_date = allocation.last_executed_carryover_date
                    carryover_level, carryover_level_idx = allocation._get_current_accrual_plan_level_id(last_carryover_date)
                    carryover_period_end = carryover_level._get_next_date(last_carryover_date)
                    if carryover_level_idx < (len(level_ids) - 1) and allocation.accrual_plan_id.transition_mode == 'immediately':
                        next_level = level_ids[carryover_level_idx + 1]
                        carryover_level_last_date = ref_date + get_timedelta(next_level.start_count, next_level.start_type)
                        carryover_period_end = min(carryover_period_end, carryover_level_last_date)
                    if carryover_level.frequency in carryover_level._get_hourly_frequencies() + ['daily']:
                        carryover_period_end = last_carryover_date
                    accrued = not allocation.already_accrued and allocation.nextcall == period_end
                    if accrued and last_carryover_date <= allocation.nextcall <= carryover_period_end:
                        if carryover_level.action_with_unused_accruals == 'lost' or carryover_level.carryover_options == 'limited':
                            allocation.last_executed_carryover_date = carryover_date
                            allocated_days_left = allocation.number_of_days - leaves_taken
                            postpone_max_days = (
                                current_level.postpone_max_days
                                if current_level.added_value_type == 'day'
                                else current_level.postpone_max_days / allocation.employee_id._get_hours_per_day(allocation.date_from)
                            )
                            allocated_days_left = allocation.number_of_days - leaves_taken
                            allocation_max_days = 0
                            if current_level.carryover_options == 'limited':
                                postpone_max_days = current_level.postpone_max_days
                                allocation_max_days = min(postpone_max_days, allocated_days_left)
                            allocation.number_of_days = min(allocation.number_of_days, allocation_max_days) + leaves_taken

                if is_accrual_date:
                    allocation.lastcall = allocation.nextcall
                allocation.actual_lastcall = allocation.nextcall
                allocation.nextcall = nextcall
                allocation.already_accrued = False
                if force_period and allocation.nextcall > date_to:
                    allocation.nextcall = date_to
                    force_period = False

            if allocation.accrual_plan_id.accrued_gain_time == 'start':
                ref_date_start = allocation._get_accrual_reference_date()
                level_start = {
                    level._get_level_transition_date(ref_date_start): level
                    for level in allocation.accrual_plan_id.level_ids
                }
                current_level = level_start.get(allocation.actual_lastcall) or current_level or allocation.accrual_plan_id.level_ids[0]
                period_start = current_level._get_previous_date(allocation.actual_lastcall)
                if current_level.cap_accrued_time:
                    if current_level.added_value_type == "day":
                        current_level_maximum_leave = current_level.maximum_leave
                    else:
                        current_level_maximum_leave = current_level.maximum_leave / allocation.employee_id._get_hours_per_day(allocation.date_from)
                if allocation.actual_lastcall in {period_start, ref_date_start} | set(level_start.keys()) or (
                    allocation.actual_lastcall - get_timedelta(current_level.accrual_validity_count, current_level.accrual_validity_type)
                    in {period_start, ref_date_start} | set(level_start.keys())
                ):
                    days_before = allocation.number_of_days
                    allocation._add_days_to_allocation(
                        current_level, current_level_maximum_leave, leaves_taken, period_start, allocation.nextcall
                    )
                    if log and allocation.number_of_days != days_before:
                        step_log = _(
                            'Accrued <b>%s</b> %s (gain at start) for period %s → %s (level: %s %s %s, %s %s/%s)'
                        ) % (
                            allocation.number_of_days - days_before,
                            allocation.holiday_status_id.request_unit in ["day", "half_day"] and _('days') or _('hours'),
                            format_date(allocation.env, period_start),
                            format_date(allocation.env, allocation.nextcall),
                            current_level.start_count,
                            current_level.start_type,
                            _('from ref'),
                            current_level.added_value,
                            current_level.added_value_type == 'day' and _('day(s)') or _('hour(s)'),
                            current_level.frequency,
                        )
                        log_parts.append('<p>%s</p>' % step_log)
                        if allocation.id and isinstance(allocation.id, int) and allocation.id > 0:
                            allocation._message_log(body=step_log)
                    allocation.already_accrued = True

            if log:
                total_log = _(
                    '<p><b>Accrual total: %s %s</b></p>'
                ) % (
                    float_round(allocation.number_of_days, precision_digits=2),
                    allocation.holiday_status_id.request_unit in ["day", "half_day"] and _('days') or _('hours'),
                )
                log_parts.append(total_log)
                if allocation.id and isinstance(allocation.id, int) and allocation.id > 0:
                    allocation._message_log(body=total_log)
            allocation.last_accrual_calculation_log = ''.join(log_parts) if log_parts else False

    def _add_lastcalls(self):
        """Override to use milestone reference date for level start when setting lastcall/nextcall."""
        for allocation in self:
            if allocation.allocation_type != 'accrual':
                continue
            today = fields.Date.today()
            (current_level, current_level_idx) = allocation._get_current_accrual_plan_level_id(today)
            if not allocation.lastcall:
                if not current_level:
                    allocation.lastcall = today
                    allocation.actual_lastcall = allocation.lastcall
                    continue
                ref_date = allocation._get_accrual_reference_date()
                allocation.lastcall = max(
                    current_level._get_previous_date(today),
                    ref_date + get_timedelta(current_level.start_count, current_level.start_type)
                )
                allocation.actual_lastcall = allocation.lastcall
            if current_level and not allocation.nextcall:
                accrual_plan = allocation.accrual_plan_id
                allocation.nextcall = current_level._get_next_date(allocation.lastcall)
                if current_level_idx < (len(accrual_plan.level_ids) - 1) and accrual_plan.transition_mode == 'immediately':
                    next_level = accrual_plan.level_ids[current_level_idx + 1]
                    ref_date = allocation._get_accrual_reference_date()
                    next_level_start = ref_date + get_timedelta(next_level.start_count, next_level.start_type)
                    allocation.nextcall = min(allocation.nextcall, next_level_start)
                expiration_date = allocation.carried_over_days_expiration_date
                if expiration_date and expiration_date > allocation.lastcall:
                    allocation.nextcall = min(allocation.nextcall, expiration_date)
