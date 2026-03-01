import logging
import json
from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.addons.resource.models.utils import HOURS_PER_DAY

OT_PRIORITY_CODES = ['OTR', 'PHO', 'OTW']  # Weekend, Public Holiday, Weekday
OT_MULTIPLIERS = {'OTW': 1.25, 'OTR': 1.5, 'PHO': 1.5}
LATENESS_CODES = ('LAT', 'LATE', 'Lateness', 'L')
_logger = logging.getLogger(__name__)

class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # Clean field names (no dashboard_*)
    lateness_hours = fields.Float(string='Lateness (hrs)', compute='_compute_lateness_and_ot', store=False)
    overtime_hours = fields.Float(string='Overtime (hrs)', compute='_compute_lateness_and_ot', store=False)
    overtime_equivalent_hours = fields.Float(string='Overtime Equivalent (hrs)', compute='_compute_lateness_and_ot', store=False)
    remaining_lateness_hours = fields.Float(string='Remaining Lateness (hrs)', compute='_compute_remaining_lateness', store=False)
    annual_leave_balance_hours = fields.Float(
        string='Annual Leave Balance (hrs)',
        compute='_compute_annual_leave_balance_hours',
        store=False,
        help='Remaining balance in hours for the configured Annual Leave type used for lateness coverage.',
    )
    remaining_annual_leave_balance_hours = fields.Float(
        string='Remaining Annual Leave Balance (hrs)',
        compute='_compute_remaining_annual_leave_balance_hours',
        store=False,
    )
    lateness_reconciled = fields.Boolean(default=False, copy=False, readonly=True)
    lateness_reconcile_snapshot = fields.Text(copy=False, readonly=True)
    lateness_reconcile_leave_id = fields.Many2one('hr.leave', copy=False, readonly=True)
    ot_wallet_carry_in_equiv = fields.Float(copy=False, readonly=True, default=0.0)
    ot_wallet_earned_equiv = fields.Float(copy=False, readonly=True, default=0.0)
    ot_wallet_lateness_consumed_equiv = fields.Float(copy=False, readonly=True, default=0.0)
    ot_wallet_payout_equiv = fields.Float(copy=False, readonly=True, default=0.0)
    ot_wallet_total_before_deduction_equiv = fields.Float(
        string='OT balance',
        compute='_compute_ot_wallet_total_before_deduction_equiv',
        store=True,
        readonly=True,
        copy=False,
    )
    ot_wallet_consumed_equiv = fields.Float(copy=False, readonly=True, default=0.0)
    ot_wallet_carry_out_equiv = fields.Float(copy=False, readonly=True, default=0.0)
    annual_leave_hours_before = fields.Float(
        string='Annual Leave Hours before',
        compute='_compute_before_after_reconcile_values',
        store=False,
    )
    ot_balance_before = fields.Float(
        string='OT balance before',
        compute='_compute_before_after_reconcile_values',
        store=False,
    )
    lateness_before = fields.Float(
        string='Lateness before',
        compute='_compute_before_after_reconcile_values',
        store=False,
    )
    annual_leave_hours_after = fields.Float(
        string='Annual Leave Hours after',
        compute='_compute_before_after_reconcile_values',
        store=False,
    )
    ot_balance_after = fields.Float(
        string='OT balance after',
        compute='_compute_before_after_reconcile_values',
        store=False,
    )
    lateness_after = fields.Float(
        string='Lateness after',
        compute='_compute_before_after_reconcile_values',
        store=False,
    )

    def _build_lateness_snapshot(self):
        """Capture original worked days and REMLATE before reconciliation."""
        self.ensure_one()
        remlate_input = self.input_line_ids.filtered(lambda l: (l.code or '').strip() == 'REMLATE')[:1]
        snapshot_lateness, snapshot_buckets = self._get_worked_day_hours_by_code()
        return {
            'worked_days_hours': {str(line.id): (line.number_of_hours or 0.0) for line in self.worked_days_line_ids},
            # Keep wallet source totals independent from worked_days line IDs.
            # Some flows recreate worked day lines after leave creation/approval.
            'wallet_source_lateness': snapshot_lateness,
            'wallet_source_buckets': snapshot_buckets,
            'remlate_amount': remlate_input.amount if remlate_input else None,
            'ot_wallet_carry_in_equiv': self.ot_wallet_carry_in_equiv,
            'ot_wallet_earned_equiv': self.ot_wallet_earned_equiv,
            'ot_wallet_lateness_consumed_equiv': self.ot_wallet_lateness_consumed_equiv,
            'ot_wallet_payout_equiv': self.ot_wallet_payout_equiv,
            'ot_wallet_consumed_equiv': self.ot_wallet_consumed_equiv,
            'ot_wallet_carry_out_equiv': self.ot_wallet_carry_out_equiv,
            'ot_payout_signature': self._get_ot_payout_snapshot_signature(),
            'created_leave_ids': [],
        }

    def _restore_lateness_snapshot(self):
        """Restore worked days and REMLATE from the stored snapshot."""
        self.ensure_one()
        if not self.lateness_reconcile_snapshot:
            return

        try:
            payload = json.loads(self.lateness_reconcile_snapshot)
        except Exception:
            return

        for line_id_str, hours in (payload.get('worked_days_hours') or {}).items():
            line = self.env['hr.payslip.worked_days'].browse(int(line_id_str)).exists()
            if line and line.payslip_id == self:
                line.number_of_hours = hours or 0.0

        remlate_amount = payload.get('remlate_amount')
        inp = self.input_line_ids.filtered(lambda l: (l.code or '').strip() == 'REMLATE')
        if remlate_amount is None:
            if inp:
                inp.unlink()
        else:
            if inp:
                inp.write({'amount': remlate_amount})
            else:
                remlate_input_type = self._get_remlate_input_type()
                self.env['hr.payslip.input'].create({
                    'payslip_id': self.id,
                    'name': remlate_input_type.name or 'Remaining Lateness (hrs)',
                    'input_type_id': remlate_input_type.id,
                    'amount': remlate_amount,
                })

        self.write({
            'ot_wallet_carry_in_equiv': payload.get('ot_wallet_carry_in_equiv', 0.0),
            'ot_wallet_earned_equiv': payload.get('ot_wallet_earned_equiv', 0.0),
            'ot_wallet_lateness_consumed_equiv': payload.get('ot_wallet_lateness_consumed_equiv', 0.0),
            'ot_wallet_payout_equiv': payload.get('ot_wallet_payout_equiv', 0.0),
            'ot_wallet_consumed_equiv': payload.get('ot_wallet_consumed_equiv', 0.0),
            'ot_wallet_carry_out_equiv': payload.get('ot_wallet_carry_out_equiv', 0.0),
        })

    def _get_hourly_rate_for_ot_payout(self):
        self.ensure_one()
        wage = 0.0
        if self.employee_id and hasattr(self.employee_id, 'wage'):
            wage = self.employee_id.wage or 0.0
        if not wage and self.contract_id:
            wage = self.contract_id.wage or 0.0
        return wage / 240.0 if wage else 0.0

    def _get_ot_payout_hours_from_inputs(self):
        self.ensure_one()
        return self._get_ot_wallet_deduction_hours_from_inputs()

    def _get_ot_wallet_deduction_hours_from_inputs(self):
        self.ensure_one()
        return sum(
            self.input_line_ids.filtered(
                lambda l: l.is_ot_payout or l.is_ot_leave_conversion
            ).mapped('hours')
        )

    def _get_ot_payout_snapshot_signature(self):
        self.ensure_one()
        signature = []
        for line in self.input_line_ids.filtered(lambda l: l.is_ot_payout).sorted('id'):
            signature.append({
                'line_id': line.id,
                'input_type_id': line.input_type_id.id,
                'hours': round(line.hours or 0.0, 6),
                'amount': round(line.amount or 0.0, 6),
            })
        return signature

    def _get_ot_payout_debug_lines(self):
        self.ensure_one()
        return [{
            'line_id': line.id,
            'name': line.name,
            'input_type_id': line.input_type_id.id,
            'input_type': line.input_type_id.display_name,
            'is_ot_payout': bool(line.is_ot_payout),
            'is_ot_leave_conversion': bool(line.is_ot_leave_conversion),
            'hours': line.hours or 0.0,
            'amount': line.amount or 0.0,
        } for line in self.input_line_ids.filtered(
            lambda l: l.is_ot_payout or l.is_ot_leave_conversion
        ).sorted('id')]

    def _get_ot_wallet_available_before_lateness(self):
        """OT available for manual deduction before lateness coverage for this payslip."""
        self.ensure_one()
        lateness, buckets = self._get_worked_day_hours_by_code()
        carry_in = self._get_previous_ot_wallet_carry_out()
        weighted_total = self._get_weighted_ot_hours(buckets)
        used_deduction_hours = self._get_ot_wallet_deduction_hours_from_inputs()
        available = max((carry_in + weighted_total) - used_deduction_hours, 0.0)
        _logger.info(
            "[OTWallet] available_before_lateness slip_id=%s carry_in=%s weighted_total=%s used_deduction_hours=%s available=%s lateness=%s",
            self.id, carry_in, weighted_total, used_deduction_hours, available, lateness
        )
        return available

    def _get_ot_leave_conversion_input_type(self):
        """Return an input type dedicated to OT->Leave conversion, creating it if needed."""
        self.ensure_one()
        input_type_model = self.env['hr.payslip.input.type'].sudo()
        company_country = self.company_id.country_id

        input_type = input_type_model.search([
            ('code', '=', 'OT2LEAVE'),
            ('country_id', '=', company_country.id),
        ], limit=1)
        if not input_type:
            input_type = input_type_model.search([('code', '=', 'OT2LEAVE')], limit=1)
        if not input_type:
            vals = {
                'name': _('Overtime to Annual Leave'),
                'code': 'OT2LEAVE',
                'is_ot_leave_conversion': True,
            }
            if company_country:
                vals['country_id'] = company_country.id
            input_type = input_type_model.create(vals)
        elif not input_type.is_ot_leave_conversion:
            input_type.write({'is_ot_leave_conversion': True})
        return input_type

    def _get_ot_wallet_before_payout_equiv(self):
        self.ensure_one()
        total_before = (self.ot_wallet_carry_in_equiv or 0.0) + (self.ot_wallet_earned_equiv or 0.0)
        return max(total_before - (self.ot_wallet_lateness_consumed_equiv or 0.0), 0.0)

    def _get_ot_balance_after_value(self):
        """Return OT balance after using the same functional logic used by `ot_balance_after`."""
        self.ensure_one()
        lateness, buckets = self._get_worked_day_hours_by_code()
        carry_in = self.ot_wallet_carry_in_equiv or self._get_previous_ot_wallet_carry_out()
        weighted_total = self._get_weighted_ot_hours(buckets)
        ot_before_payout = max(carry_in + weighted_total, 0.0)
        payout_hours = self._get_ot_payout_hours_from_inputs()
        computed_not_reconciled = max(ot_before_payout - payout_hours, 0.0)
        result = computed_not_reconciled
        source = 'computed_not_reconciled'
        if not self.lateness_reconciled:
            pass
        else:
            # Use the stored wallet carry_out as-is (including 0.0), do not fallback with `or`.
            result = self.ot_wallet_carry_out_equiv
            source = 'stored_carry_out_reconciled'

        _logger.info(
            "[OTWallet] ot_balance_after_value slip_id=%s employee_id=%s state=%s reconciled=%s "
            "date_from=%s date_to=%s lateness=%s buckets=%s carry_in_field=%s carry_in_effective=%s "
            "earned=%s ot_before_payout=%s payout_input_hours=%s computed_not_reconciled=%s "
            "stored_carry_out=%s source=%s result=%s",
            self.id,
            self.employee_id.id if self.employee_id else False,
            self.state,
            self.lateness_reconciled,
            self.date_from,
            self.date_to,
            lateness,
            buckets,
            self.ot_wallet_carry_in_equiv,
            carry_in,
            weighted_total,
            ot_before_payout,
            payout_hours,
            computed_not_reconciled,
            self.ot_wallet_carry_out_equiv,
            source,
            result,
        )
        return result

    def _get_ot_wallet_salary_amount(self):
        """Amount = OT wallet equivalent hours x hourly rate, without applying OT multipliers again."""
        self.ensure_one()
        return (self.ot_wallet_carry_out_equiv or 0.0) * self._get_hourly_rate_for_ot_payout()

    def _recompute_ot_wallet_after_payout(self):
        """Idempotent recalculation entrypoint after OT payout input changes."""
        slips = self.filtered('employee_id')
        if not slips:
            return True
        _logger.info(
            "[OTWallet] recompute_after_payout trigger_slip_ids=%s details=%s",
            slips.ids,
            [{
                'slip_id': s.id,
                'name': s.display_name,
                'state': s.state,
                'reconciled': s.lateness_reconciled,
                'carry_in': s.ot_wallet_carry_in_equiv,
                'earned': s.ot_wallet_earned_equiv,
                'lateness_consumed': s.ot_wallet_lateness_consumed_equiv,
                'payout_field': s.ot_wallet_payout_equiv,
                'carry_out': s.ot_wallet_carry_out_equiv,
                'payout_input_hours': s._get_ot_payout_hours_from_inputs(),
                'payout_inputs': s._get_ot_payout_debug_lines(),
            } for s in slips],
        )
        # Rebuild whole chain so carry-forward stays consistent after any payout edit.
        slips.action_rebuild_ot_wallet()
        return True

    def _assert_ot_payout_snapshot_integrity(self):
        """Prevent hidden modifications of OT payout inputs after reconciliation."""
        for slip in self.filtered('lateness_reconciled'):
            if not slip.lateness_reconcile_snapshot:
                continue
            try:
                payload = json.loads(slip.lateness_reconcile_snapshot) or {}
            except Exception:
                continue
            expected_signature = payload.get('ot_payout_signature', [])
            current_signature = slip._get_ot_payout_snapshot_signature()
            if expected_signature != current_signature:
                raise ValidationError(_(
                    'OT payout inputs were changed after reconciliation for %(payslip)s.\n'
                    'Use "Reset Reconciliation", update OT payout hours, then run "Reconcile Lateness" again.'
                ) % {
                    'payslip': slip.display_name,
                })

    def _apply_ot_payout_wallet_deduction(self):
        for slip in self:
            payout_hours = slip._get_ot_payout_hours_from_inputs()
            if not payout_hours and not slip.ot_wallet_payout_equiv:
                continue
            if payout_hours and not slip.lateness_reconciled:
                _logger.warning(
                    "[OTWallet] direct_apply_failed_not_reconciled slip_id=%s payout_hours=%s payout_inputs=%s",
                    slip.id, payout_hours, slip._get_ot_payout_debug_lines()
                )
                raise ValidationError(_('You must run Lateness Reconciliation before OT payout.'))
            wallet_before_payout = slip._get_ot_wallet_before_payout_equiv()
            if payout_hours > wallet_before_payout + 1e-6:
                _logger.warning(
                    "[OTWallet] direct_apply_validation_failed slip_id=%s wallet_before_payout=%s payout_hours=%s payout_inputs=%s",
                    slip.id, wallet_before_payout, payout_hours, slip._get_ot_payout_debug_lines()
                )
                raise ValidationError(_(
                    'OT payout hours (%(payout).2f) cannot exceed available OT Wallet (%(available).2f).'
                ) % {
                    'payout': payout_hours,
                    'available': wallet_before_payout,
                })
            slip.write({
                'ot_wallet_payout_equiv': payout_hours,
                'ot_wallet_consumed_equiv': (slip.ot_wallet_lateness_consumed_equiv or 0.0) + payout_hours,
                'ot_wallet_carry_out_equiv': max(wallet_before_payout - payout_hours, 0.0),
            })

    @api.depends(
        'worked_days_line_ids.number_of_hours',
        'worked_days_line_ids.work_entry_type_id.code',
        'employee_id',
        'date_to',
        'company_id'
    )
    def _compute_remaining_annual_leave_balance_hours(self):
        for slip in self:
            slip.remaining_annual_leave_balance_hours = 0.0

            # Current balance
            current_balance = slip.annual_leave_balance_hours or 0.0
            # If reconciliation already ran (REMLATE exists), show actual current balance.
            # The old estimate formula (lateness - OT) can be misleading after OT lines are updated.
            remlate_input = slip.input_line_ids.filtered(lambda l: (l.code or '').strip() == 'REMLATE')
            if remlate_input:
                slip.remaining_annual_leave_balance_hours = current_balance
                continue

            # Pre-reconciliation preview only.
            lateness, buckets = slip._get_worked_day_hours_by_code()
            carry_in = slip.ot_wallet_carry_in_equiv or slip._get_previous_ot_wallet_carry_out()
            total_ot_equiv = slip._get_weighted_ot_hours(buckets)
            estimated_leave_hours = max(lateness - (carry_in + total_ot_equiv), 0.0)
            slip.remaining_annual_leave_balance_hours = max(current_balance - estimated_leave_hours, 0.0)

    def _get_configured_annual_leave_type(self):
        """Return annual leave type configured in custom lateness settings."""
        self.ensure_one()
        company = self.company_id or self.env.company
        return company.sudo().lateness_annual_leave_type_id

    def _get_remlate_input_type(self):
        """Return an input type for REMLATE code, creating it if needed."""
        self.ensure_one()
        input_type_model = self.env['hr.payslip.input.type'].sudo()
        company_country = self.company_id.country_id

        input_type = input_type_model.search([
            ('code', '=', 'REMLATE'),
            ('country_id', '=', company_country.id),
        ], limit=1)
        if not input_type:
            input_type = input_type_model.search([('code', '=', 'REMLATE')], limit=1)
        if not input_type:
            vals = {
                'name': _('Remaining Lateness (hrs)'),
                'code': 'REMLATE',
            }
            if company_country:
                vals['country_id'] = company_country.id
            input_type = input_type_model.create(vals)
        return input_type

    def _get_valid_leave_slot(self, remaining_hours, leave_type):
        """Find a valid single-day leave slot within payslip period for required hours."""
        self.ensure_one()
        if remaining_hours <= 0 or not self.employee_id or not leave_type:
            return False

        Leave = self.env['hr.leave']
        day = self.date_from or self.date_to or fields.Date.today()
        end_day = self.date_to or day
        while day <= end_day:
            overlapping_leave = Leave.sudo().search([
                ('employee_id', '=', self.employee_id.id),
                ('state', 'in', ['confirm', 'validate1', 'validate']),
                ('request_date_from', '<=', day),
                ('request_date_to', '>=', day),
            ], limit=1)
            if overlapping_leave:
                day += timedelta(days=1)
                continue

            leave_preview = self.env['hr.leave'].new({
                'employee_id': self.employee_id.id,
                'holiday_status_id': leave_type.id,
                'request_date_from': day,
                'request_date_to': day,
                'request_unit_hours': True,
            })
            hour_from, hour_to = leave_preview._get_hour_from_to(day, day)
            if hour_to > hour_from and (hour_to - hour_from) >= remaining_hours:
                return day, hour_from, hour_from + remaining_hours
            day += timedelta(days=1)
        return False

    def _get_valid_leave_slots(self, remaining_hours, leave_type):
        """Build one or more day slots that together can cover remaining_hours."""
        self.ensure_one()
        if remaining_hours <= 0 or not self.employee_id or not leave_type:
            return [], remaining_hours

        Leave = self.env['hr.leave']
        slots = []
        remaining = remaining_hours
        day = self.date_from or self.date_to or fields.Date.today()
        end_day = self.date_to or day
        while day <= end_day and remaining > 0:
            # Use datetime overlap (not request_date_* only) to reliably catch
            # existing validated/confirmed leaves on that day.
            day_start = datetime.combine(day, time.min)
            day_end = datetime.combine(day, time.max)
            overlapping_leave = Leave.sudo().search([
                ('employee_id', '=', self.employee_id.id),
                ('state', 'in', ['confirm', 'validate1', 'validate']),
                ('date_from', '<=', fields.Datetime.to_string(day_end)),
                ('date_to', '>=', fields.Datetime.to_string(day_start)),
            ], limit=1)
            if overlapping_leave:
                day += timedelta(days=1)
                continue

            for hour_from, hour_to in self._get_day_attendance_hour_ranges(day):
                if remaining <= 0:
                    break
                capacity = max(hour_to - hour_from, 0.0)
                if capacity <= 0:
                    continue
                take = min(capacity, remaining)
                slot_to = hour_from + take
                leave_preview = self.env['hr.leave'].new({
                    'employee_id': self.employee_id.id,
                    'holiday_status_id': leave_type.id,
                    'request_date_from': day,
                    'request_date_to': day,
                    'request_unit_hours': True,
                    'request_hour_from': hour_from,
                    'request_hour_to': slot_to,
                })
                leave_preview._compute_date_from_to()
                if leave_preview.date_from >= leave_preview.date_to:
                    continue
                # Final guard: avoid proposing a slot that overlaps an existing leave.
                slot_overlap = Leave.sudo().search([
                    ('employee_id', '=', self.employee_id.id),
                    ('state', 'in', ['confirm', 'validate1', 'validate']),
                    ('date_from', '<', fields.Datetime.to_string(leave_preview.date_to)),
                    ('date_to', '>', fields.Datetime.to_string(leave_preview.date_from)),
                ], limit=1)
                if slot_overlap:
                    continue
                slots.append((day, hour_from, slot_to, take))
                remaining -= take
            day += timedelta(days=1)
        return slots, remaining

    def _get_day_attendance_hour_ranges(self, day):
        """Return employee work attendance ranges (hour_from, hour_to) for a given day."""
        self.ensure_one()
        employee = self.employee_id
        calendar = employee.resource_calendar_id or employee.company_id.resource_calendar_id
        if not calendar:
            return []
        employee_tz = pytz.timezone(employee.tz or calendar.tz or 'UTC')
        start_dt = pytz.utc.localize(datetime.combine(day, time.min))
        end_dt = pytz.utc.localize(datetime.combine(day, time.max))
        resource = employee.resource_id
        intervals = calendar._attendance_intervals_batch(start_dt, end_dt, resources=resource)
        day_intervals = intervals.get(resource.id if resource else False)
        if not day_intervals:
            return []
        ranges = []
        for start, end, _attendance in day_intervals._items:
            local_start = start.astimezone(employee_tz)
            local_end = end.astimezone(employee_tz)
            if local_end <= local_start:
                continue
            hour_from = local_start.hour + (local_start.minute / 60.0)
            hour_to = local_end.hour + (local_end.minute / 60.0)
            if hour_to > hour_from:
                ranges.append((hour_from, hour_to))
        return ranges

    def _get_worked_day_hours_by_code(self):
        self.ensure_one()
        buckets = {code: 0.0 for code in OT_PRIORITY_CODES}
        lateness = 0.0
        for line in self.worked_days_line_ids:
            code = (line.work_entry_type_id.code or '').strip()
            if code in buckets:
                buckets[code] += line.number_of_hours or 0.0
            # Common lateness codes - adjust in settings or extend if needed
            if code in LATENESS_CODES:
                lateness += line.number_of_hours or 0.0
        return lateness, buckets

    def _get_weighted_ot_hours(self, buckets):
        return sum((buckets.get(code, 0.0) or 0.0) * OT_MULTIPLIERS.get(code, 1.0) for code in OT_PRIORITY_CODES)

    @api.depends('ot_wallet_carry_in_equiv', 'ot_wallet_earned_equiv')
    def _compute_ot_wallet_total_before_deduction_equiv(self):
        for slip in self:
            slip.ot_wallet_total_before_deduction_equiv = (
                (slip.ot_wallet_carry_in_equiv or 0.0) + (slip.ot_wallet_earned_equiv or 0.0)
            )

    @api.depends(
        'lateness_reconciled',
        'lateness_reconcile_snapshot',
        'annual_leave_balance_hours',
        'remaining_lateness_hours',
        'worked_days_line_ids.number_of_hours',
        'worked_days_line_ids.work_entry_type_id.code',
        'ot_wallet_carry_out_equiv',
    )
    def _compute_before_after_reconcile_values(self):
        for slip in self:
            lateness, buckets = slip._get_worked_day_hours_by_code()
            carry_in = slip.ot_wallet_carry_in_equiv or slip._get_previous_ot_wallet_carry_out()
            current_ot_before = carry_in + slip._get_weighted_ot_hours(buckets)
            current_annual = slip.annual_leave_balance_hours or 0.0
            current_lateness = lateness

            if not slip.lateness_reconciled:
                slip.annual_leave_hours_before = current_annual
                slip.ot_balance_before = current_ot_before
                slip.lateness_before = current_lateness
                slip.annual_leave_hours_after = current_annual
                slip.ot_balance_after = slip._get_ot_balance_after_value()
                slip.lateness_after = current_lateness
                continue

            before_annual = current_annual
            before_ot = current_ot_before
            before_lateness = current_lateness
            if slip.lateness_reconcile_snapshot:
                try:
                    payload = json.loads(slip.lateness_reconcile_snapshot)
                    before_annual = payload.get('annual_leave_hours_before', before_annual)
                    before_ot = payload.get('ot_balance_before', before_ot)
                    before_lateness = payload.get('lateness_before', before_lateness)
                except Exception:
                    pass

            slip.annual_leave_hours_before = before_annual
            slip.ot_balance_before = before_ot
            slip.lateness_before = before_lateness
            slip.annual_leave_hours_after = current_annual
            slip.ot_balance_after = slip._get_ot_balance_after_value()
            slip.lateness_after = slip.remaining_lateness_hours or 0.0

    def _get_previous_ot_wallet_carry_out(self):
        """Compute cumulative OT wallet carry before current slip from all previous months."""
        self.ensure_one()
        previous_slips = self.search([
            ('employee_id', '=', self.employee_id.id),
            ('id', '!=', self.id),
            ('state', '!=', 'cancel'),
            '|',
            ('date_to', '<', self.date_to),
            '&',
            ('date_to', '=', self.date_to),
            ('id', '<', self.id),
        ], order='date_to asc, id asc')

        carry = 0.0
        _logger.info(
            "[OTWallet] chain_start current_slip_id=%s employee_id=%s previous_count=%s",
            self.id, self.employee_id.id, len(previous_slips),
        )
        for slip in previous_slips:
            lateness, buckets = slip._get_wallet_source_hours()
            earned = slip._get_weighted_ot_hours(buckets)
            payout = slip._get_ot_payout_hours_from_inputs() if slip.lateness_reconciled else 0.0
            carry_before = carry
            wallet_before_payout = carry + earned
            if payout > wallet_before_payout + 1e-6:
                _logger.warning(
                    "[OTWallet] chain_validation_failed current_slip_id=%s previous_slip_id=%s previous_name=%s previous_reconciled=%s "
                    "carry_before=%s earned=%s lateness=%s consumed=%s wallet_before_payout=%s payout=%s payout_inputs=%s",
                    self.id,
                    slip.id,
                    slip.display_name,
                    slip.lateness_reconciled,
                    carry_before,
                    earned,
                    lateness,
                    0.0,
                    wallet_before_payout,
                    payout,
                    slip._get_ot_payout_debug_lines(),
                )
                raise ValidationError(_(
                    'OT payout hours (%(payout).2f) exceed available OT Wallet (%(available).2f) on payslip %(payslip)s.'
                ) % {
                    'payout': payout,
                    'available': wallet_before_payout,
                    'payslip': slip.display_name,
                })
            wallet_after_payout = max(wallet_before_payout - payout, 0.0)
            consumed = min(lateness, wallet_after_payout)
            carry = max(wallet_after_payout - consumed, 0.0)
            _logger.info(
                "[OTWallet] previous slip_id=%s date_to=%s lateness=%s otw=%s otr=%s pho=%s earned_equiv=%s carry_in=%s consumed=%s payout=%s carry_out=%s",
                slip.id,
                slip.date_to,
                lateness,
                buckets.get('OTW', 0.0),
                buckets.get('OTR', 0.0),
                buckets.get('PHO', 0.0),
                earned,
                carry_before,
                consumed,
                payout,
                carry,
            )
        _logger.info(
            "[OTWallet] chain_end current_slip_id=%s carry_in=%s",
            self.id, carry,
        )
        return carry

    def _get_wallet_source_hours(self):
        """Return lateness and OT buckets from original values if snapshot exists."""
        self.ensure_one()
        if not (self.lateness_reconciled and self.lateness_reconcile_snapshot):
            return self._get_worked_day_hours_by_code()

        try:
            payload = json.loads(self.lateness_reconcile_snapshot)
        except Exception:
            return self._get_worked_day_hours_by_code()

        snapshot_buckets = payload.get('wallet_source_buckets')
        snapshot_lateness = payload.get('wallet_source_lateness')
        if isinstance(snapshot_buckets, dict) and snapshot_lateness is not None:
            buckets = {code: float(snapshot_buckets.get(code, 0.0) or 0.0) for code in OT_PRIORITY_CODES}
            return float(snapshot_lateness or 0.0), buckets

        original_hours = payload.get('worked_days_hours') or {}
        buckets = {code: 0.0 for code in OT_PRIORITY_CODES}
        lateness = 0.0
        for line in self.worked_days_line_ids:
            code = (line.work_entry_type_id.code or '').strip()
            hours = original_hours.get(str(line.id), line.number_of_hours or 0.0)
            if code in buckets:
                buckets[code] += hours or 0.0
            if code in LATENESS_CODES:
                lateness += hours or 0.0
        return lateness, buckets

    def action_rebuild_ot_wallet(self):
        """Rebuild OT wallet chain for employee across payslips chronologically."""
        employees = self.mapped('employee_id').exists()
        if not employees:
            raise UserError(_('Employee is required to rebuild OT wallet.'))

        for employee in employees:
            slips = self.search([
                ('employee_id', '=', employee.id),
                ('state', '!=', 'cancel'),
            ], order='date_to asc, id asc')

            carry_in = 0.0
            _logger.info(
                "[OTWallet] rebuild_start trigger_slip_ids=%s employee_id=%s slips=%s",
                self.ids, employee.id, len(slips),
            )
            for slip in slips:
                lateness, buckets = slip._get_wallet_source_hours()
                earned = slip._get_weighted_ot_hours(buckets)
                payout = slip._get_ot_payout_hours_from_inputs() if slip.lateness_reconciled else 0.0
                wallet_before_payout = carry_in + earned
                if payout > wallet_before_payout + 1e-6:
                    _logger.warning(
                        "[OTWallet] rebuild_validation_failed trigger_slip_ids=%s employee_id=%s slip_id=%s slip_name=%s "
                        "reconciled=%s carry_in=%s earned=%s lateness=%s consumed=%s wallet_before_payout=%s payout=%s payout_inputs=%s",
                        self.ids,
                        employee.id,
                        slip.id,
                        slip.display_name,
                        slip.lateness_reconciled,
                        carry_in,
                        earned,
                        lateness,
                        0.0,
                        wallet_before_payout,
                        payout,
                        slip._get_ot_payout_debug_lines(),
                    )
                    raise ValidationError(_(
                        'OT payout hours (%(payout).2f) exceed available OT Wallet (%(available).2f) on payslip %(payslip)s.'
                    ) % {
                        'payout': payout,
                        'available': wallet_before_payout,
                        'payslip': slip.display_name,
                    })
                wallet_after_payout = max(wallet_before_payout - payout, 0.0)
                consumed = min(lateness, wallet_after_payout)
                carry_out = max(wallet_after_payout - consumed, 0.0)
                slip.write({
                    'ot_wallet_carry_in_equiv': carry_in,
                    'ot_wallet_earned_equiv': earned,
                    'ot_wallet_lateness_consumed_equiv': consumed,
                    'ot_wallet_payout_equiv': payout,
                    'ot_wallet_consumed_equiv': consumed + payout,
                    'ot_wallet_carry_out_equiv': carry_out,
                })
                _logger.info(
                    "[OTWallet] rebuild slip_id=%s date_to=%s lateness=%s otw=%s otr=%s pho=%s carry_in=%s earned=%s consumed=%s payout=%s carry_out=%s",
                    slip.id,
                    slip.date_to,
                    lateness,
                    buckets.get('OTW', 0.0),
                    buckets.get('OTR', 0.0),
                    buckets.get('PHO', 0.0),
                    carry_in,
                    earned,
                    consumed,
                    payout,
                    carry_out,
                )
                carry_in = carry_out
            _logger.info(
                "[OTWallet] rebuild_end trigger_slip_ids=%s employee_id=%s final_carry=%s",
                self.ids, employee.id, carry_in,
            )
        return True

    @api.depends('worked_days_line_ids.number_of_hours', 'worked_days_line_ids.work_entry_type_id.code')
    def _compute_lateness_and_ot(self):
        for slip in self:
            lateness, buckets = slip._get_worked_day_hours_by_code()
            slip.lateness_hours = lateness
            slip.overtime_hours = sum(buckets.values())
            slip.overtime_equivalent_hours = slip._get_weighted_ot_hours(buckets)

    @api.depends(
        'worked_days_line_ids.number_of_hours',
        'worked_days_line_ids.work_entry_type_id.code',
        'input_line_ids.amount',
        'input_line_ids.code',
    )
    def _compute_remaining_lateness(self):
        # After reconciliation, remaining is stored in input line code REMLATE.
        # Before reconciliation, preview remaining as lateness minus overtime buckets.
        for slip in self:
            inp = slip.input_line_ids.filtered(lambda l: (l.code or '').strip() == 'REMLATE')
            if inp:
                rem = sum(inp.mapped('amount'))
            else:
                lateness, buckets = slip._get_worked_day_hours_by_code()
                carry_in = slip.ot_wallet_carry_in_equiv or slip._get_previous_ot_wallet_carry_out()
                payout = slip._get_ot_payout_hours_from_inputs()
                available_after_payout = max((carry_in + slip._get_weighted_ot_hours(buckets)) - payout, 0.0)
                rem = max(lateness - available_after_payout, 0.0)
            slip.remaining_lateness_hours = rem

    @api.depends('employee_id', 'date_to', 'company_id')
    def _compute_annual_leave_balance_hours(self):
        for slip in self:
            slip.annual_leave_balance_hours = 0.0
            leave_type = slip._get_configured_annual_leave_type()
            if not leave_type or not slip.employee_id:
                continue

            consumed_leaves, _extra_data = slip.employee_id._get_consumed_leaves(
                leave_type,
                target_date=slip.date_to or fields.Date.today(),
            )
            allocations_data = consumed_leaves.get(slip.employee_id, {}).get(leave_type, {})
            remaining = sum(data.get('virtual_remaining_leaves', 0.0) for data in allocations_data.values())
            if leave_type.request_unit in ('day', 'half_day'):
                remaining *= slip.employee_id.resource_calendar_id.hours_per_day or HOURS_PER_DAY
            slip.annual_leave_balance_hours = remaining

    def action_reconcile_lateness_no_ot_bank(self):
        """Core reconciliation:
        - Consume OT hours in order OTR -> PHO -> OTW by reducing worked days OT hours.
        - If still remaining, create a Time Off (hr.leave) request in HOURS against configured Annual Leave type.
        - If still remaining, store hours into payslip input line code REMLATE (for salary deduction rule).
        """
        Leave = self.env['hr.leave']
        # Always rebuild wallet chain first so carry values are up-to-date before reconciliation.
        self.action_rebuild_ot_wallet()
        skip_reconciled = self.env.context.get('skip_reconciled') or len(self) > 1
        for slip in self:
            leave_deduction_status = 'not_needed'
            if slip.lateness_reconciled:
                if skip_reconciled:
                    _logger.info(
                        "[LatenessReconcile] skipped_already_reconciled slip_id=%s employee_id=%s",
                        slip.id, slip.employee_id.id
                    )
                    continue
                raise UserError(_('Lateness reconciliation already applied. Use "Reset Reconciliation" first.'))

            snapshot = slip._build_lateness_snapshot()
            remlate_input_type = slip._get_remlate_input_type()
            lateness, buckets = slip._get_worked_day_hours_by_code()
            created_leave = self.env['hr.leave']
            carry_in = slip._get_previous_ot_wallet_carry_out()
            weighted_total = slip._get_weighted_ot_hours(buckets)
            payout_hours = slip._get_ot_payout_hours_from_inputs()
            snapshot.update({
                'annual_leave_hours_before': slip.annual_leave_balance_hours or 0.0,
                'ot_balance_before': carry_in + weighted_total,
                'lateness_before': lateness,
            })
            _logger.info(
                "[LatenessReconcile] start slip_id=%s name=%s employee_id=%s lateness=%s carry_in=%s buckets=%s weighted_total=%s",
                slip.id, slip.name, slip.employee_id.id, lateness, carry_in, buckets, weighted_total
            )
            _logger.info(
                "[OTWallet] current slip_id=%s date_from=%s date_to=%s lateness=%s otw=%s otr=%s pho=%s earned_equiv=%s carry_in=%s",
                slip.id,
                slip.date_from,
                slip.date_to,
                lateness,
                buckets.get('OTW', 0.0),
                buckets.get('OTR', 0.0),
                buckets.get('PHO', 0.0),
                weighted_total,
                carry_in,
            )
            _logger.info(
                "[LatenessReconcile] payout_first slip_id=%s payout_hours=%s wallet_before_lateness=%s",
                slip.id, payout_hours, carry_in + weighted_total
            )
            _logger.info(
                "[LatenessReconcile] payout_inputs slip_id=%s inputs=%s",
                slip.id, slip._get_ot_payout_debug_lines(),
            )

            wallet_before_lateness = carry_in + weighted_total
            if payout_hours > wallet_before_lateness + 1e-6:
                _logger.warning(
                    "[LatenessReconcile] payout_validation_failed slip_id=%s slip_name=%s lateness=%s carry_in=%s weighted_total=%s "
                    "wallet_before_lateness=%s payout_hours=%s payout_inputs=%s",
                    slip.id,
                    slip.display_name,
                    lateness,
                    carry_in,
                    weighted_total,
                    wallet_before_lateness,
                    payout_hours,
                    slip._get_ot_payout_debug_lines(),
                )
                raise ValidationError(_(
                    'OT payout hours (%(payout).2f) cannot exceed OT Wallet available before lateness (%(available).2f).'
                ) % {
                    'payout': payout_hours,
                    'available': wallet_before_lateness,
                })

            payout_remaining = payout_hours
            payout_from_carry = min(carry_in, payout_remaining)
            carry_in_after_payout = carry_in - payout_from_carry
            payout_remaining -= payout_from_carry

            remaining = lateness

            # 1) consume previously carried OT wallet first (equivalent hours).
            consume_wallet_equiv = min(carry_in_after_payout, remaining)
            remaining -= consume_wallet_equiv

            # 2) consume current OT buckets by weighted equivalent value, then convert back to raw OT hours.
            consumed_current_equiv = 0.0
            for code in OT_PRIORITY_CODES:
                if remaining <= 0:
                    break
                available_raw = buckets.get(code, 0.0)
                multiplier = OT_MULTIPLIERS.get(code, 1.0)
                available_equiv = available_raw * multiplier
                if available_equiv <= 0:
                    continue
                reserved_for_payout_equiv = min(available_equiv, payout_remaining)
                payout_remaining -= reserved_for_payout_equiv
                available_for_lateness_equiv = max(available_equiv - reserved_for_payout_equiv, 0.0)
                if available_for_lateness_equiv <= 0:
                    continue
                consume_equiv = min(available_for_lateness_equiv, remaining)
                consume_raw = consume_equiv / multiplier if multiplier else 0.0
                _logger.info(
                    "[LatenessReconcile] consume_ot slip_id=%s code=%s available_raw=%s available_equiv=%s reserved_for_payout_equiv=%s consume_equiv=%s consume_raw=%s remaining_before=%s",
                    slip.id, code, available_raw, available_equiv, reserved_for_payout_equiv, consume_equiv, consume_raw, remaining
                )

                # Reduce hours from worked days lines for that code (FIFO)
                lines = slip.worked_days_line_ids.filtered(lambda l: (l.work_entry_type_id.code or '').strip() == code).sorted('id')
                to_consume = consume_raw
                for line in lines:
                    if to_consume <= 0:
                        break
                    h = line.number_of_hours or 0.0
                    if h <= 0:
                        continue
                    cut = min(h, to_consume)
                    line.number_of_hours = h - cut
                    to_consume -= cut

                remaining -= consume_equiv
                consumed_current_equiv += consume_equiv
                _logger.info(
                    "[LatenessReconcile] after_ot slip_id=%s code=%s remaining_after=%s",
                    slip.id, code, remaining
                )

            # 2) if remaining > 0, deduct from Annual Leave in hours (Time Off)
            if remaining > 0:
                leave_deduction_status = 'pending'
                leave_type = slip._get_configured_annual_leave_type()
                if not leave_type:
                    raise UserError(_(
                        'Annual Leave Type for lateness coverage is not configured.\n'
                        'Go to Payroll Settings > Lateness Coverage and set Annual Leave Type for Lateness.'
                    ))

                # Never create leave beyond available annual leave balance.
                # If balance is 0, keep all remaining lateness in REMLATE.
                annual_leave_available = max(slip.annual_leave_balance_hours or 0.0, 0.0)
                leave_hours_to_deduct = min(remaining, annual_leave_available)
                _logger.info(
                    "[LatenessReconcile] leave_balance_cap slip_id=%s remaining=%s annual_leave_available=%s leave_hours_to_deduct=%s",
                    slip.id, remaining, annual_leave_available, leave_hours_to_deduct
                )
                if leave_hours_to_deduct <= 0:
                    leave_deduction_status = 'no_leave_balance'
                    _logger.warning(
                        "[LatenessReconcile] skip_leave_zero_balance slip_id=%s remaining=%s annual_leave_available=%s; keep REMLATE",
                        slip.id, remaining, annual_leave_available
                    )

                # If allocation is required but unavailable, keep remaining for payroll deduction (REMLATE)
                # instead of crashing with "There is no valid allocation to cover that request."
                if leave_hours_to_deduct > 0:
                    has_valid_allocation = leave_type.with_context(employee_id=slip.employee_id.id).has_valid_allocation
                    _logger.info(
                        "[LatenessReconcile] leave_check slip_id=%s leave_type_id=%s leave_type_name=%s request_unit=%s allows_negative=%s requires_allocation=%s has_valid_allocation=%s remaining=%s annual_leave_balance=%s",
                        slip.id, leave_type.id, leave_type.name, leave_type.request_unit, leave_type.allows_negative,
                        leave_type.requires_allocation, has_valid_allocation, remaining, slip.annual_leave_balance_hours
                    )
                    if not (leave_type.requires_allocation and not has_valid_allocation):
                        try:
                            slip_ref = slip.name or _('Payslip')
                            leave_slots, uncovered = slip._get_valid_leave_slots(leave_hours_to_deduct, leave_type)
                            if not leave_slots or uncovered > 0:
                                _logger.warning(
                                    "[LatenessReconcile] no_valid_leave_slot slip_id=%s remaining=%s leave_hours_to_deduct=%s uncovered=%s slots=%s; fallback to REMLATE",
                                    slip.id, remaining, leave_hours_to_deduct, uncovered, leave_slots
                                )
                                leave_deduction_status = 'no_valid_slot'
                                raise ValidationError(_("No valid working slot found for this leave request."))
                            created_leaves = self.env['hr.leave']
                            created_hours = 0.0
                            for leave_day, start_hour, end_hour, slot_hours in leave_slots:
                                # Re-check overlap at creation time using both business dates and datetimes,
                                # because timezone conversions can make day-only checks miss collisions.
                                leave_preview = self.env['hr.leave'].new({
                                    'employee_id': slip.employee_id.id,
                                    'holiday_status_id': leave_type.id,
                                    'request_date_from': leave_day,
                                    'request_date_to': leave_day,
                                    'request_unit_hours': True,
                                    'request_hour_from': start_hour,
                                    'request_hour_to': end_hour,
                                })
                                leave_preview._compute_date_from_to()
                                overlap_domain = [
                                    ('employee_id', '=', slip.employee_id.id),
                                    ('state', 'in', ['confirm', 'validate1', 'validate']),
                                    '|',
                                    '&',
                                    ('request_date_from', '<=', leave_day),
                                    ('request_date_to', '>=', leave_day),
                                    '&',
                                    ('date_from', '<', fields.Datetime.to_string(leave_preview.date_to)),
                                    ('date_to', '>', fields.Datetime.to_string(leave_preview.date_from)),
                                ]
                                overlap_leave = Leave.sudo().search(overlap_domain, limit=1)
                                if overlap_leave:
                                    _logger.info(
                                        "[LatenessReconcile] skip_slot_overlap slip_id=%s leave_day=%s start_hour=%s end_hour=%s overlap_leave_id=%s",
                                        slip.id, leave_day, start_hour, end_hour, overlap_leave.id
                                    )
                                    continue
                                _logger.info(
                                    "[LatenessReconcile] leave_slot_ok slip_id=%s leave_day=%s start_hour=%s end_hour=%s slot_hours=%s",
                                    slip.id, leave_day, start_hour, end_hour, slot_hours
                                )
                                leave_vals = {
                                    'name': _('Lateness Coverage (%s)') % slip_ref,
                                    'employee_id': slip.employee_id.id,
                                    'holiday_status_id': leave_type.id,
                                    'request_date_from': leave_day,
                                    'request_date_to': leave_day,
                                    'request_unit_hours': True,
                                    'request_hour_from': start_hour,
                                    'request_hour_to': end_hour,
                                    'lateness_reconcile_generated': True,
                                    'lateness_reconcile_reason': _('Generated from Lateness Reconciliation'),
                                    'lateness_reconcile_payslip_id': slip.id,
                                }
                                _logger.info(
                                    "[LatenessReconcile] creating_leave slip_id=%s leave_vals=%s",
                                    slip.id, leave_vals
                                )
                                leave = Leave.sudo().create(leave_vals)
                                if hasattr(leave, 'action_approve'):
                                    leave.sudo().action_approve(check_state=False)
                                created_leaves |= leave
                                created_hours += slot_hours
                            if not created_leaves:
                                leave_deduction_status = 'no_valid_slot'
                                _logger.warning(
                                    "[LatenessReconcile] no_slot_created_after_overlap_check slip_id=%s remaining=%s leave_hours_to_deduct=%s; fallback to REMLATE",
                                    slip.id, remaining, leave_hours_to_deduct
                                )
                                raise ValidationError(_("No valid working slot found for this leave request."))
                            created_leave = created_leaves[:1]
                            snapshot['created_leave_ids'] = created_leaves.ids
                            leave_deduction_status = 'leave_created'
                            _logger.info(
                                "[LatenessReconcile] leave_created slip_id=%s leave_ids=%s total_hours=%s",
                                slip.id, created_leaves.ids, sum(created_leaves.mapped('number_of_hours'))
                            )
                            remaining = max(remaining - created_hours, 0.0)
                        except (ValidationError, UserError) as err:
                            if leave_deduction_status == 'pending':
                                leave_deduction_status = 'leave_create_failed'
                            _logger.warning(
                                "[LatenessReconcile] leave_create_failed slip_id=%s remaining=%s error=%s; fallback to REMLATE",
                                slip.id, remaining, err
                            )
                            pass
                    else:
                        leave_deduction_status = 'no_valid_allocation'
                        _logger.warning(
                            "[LatenessReconcile] skip_leave_no_valid_allocation slip_id=%s leave_type_id=%s remaining=%s; fallback to REMLATE",
                            slip.id, leave_type.id, remaining
                        )

            # 3) Store final remaining lateness for payroll deduction rule (input line)
            # and as the post-reconciliation source for lateness_after display.
            remaining = 0.0 if remaining <= 1e-6 else round(remaining, 6)
            inp = slip.input_line_ids.filtered(lambda l: (l.code or '').strip() == 'REMLATE')
            if inp:
                inp.write({'amount': remaining})
            else:
                self.env['hr.payslip.input'].create({
                    'payslip_id': slip.id,
                    'name': remlate_input_type.name or 'Remaining Lateness (hrs)',
                    'input_type_id': remlate_input_type.id,
                    'amount': remaining,
                })
            carry_out_equiv = max(
                carry_in + weighted_total - (consume_wallet_equiv + consumed_current_equiv + payout_hours),
                0.0
            )
            _logger.info(
                "[LatenessReconcile] finalize slip_id=%s lateness_before=%s carry_in=%s earned=%s "
                "consumed_from_carry=%s consumed_from_current=%s consumed_for_lateness_total=%s payout_hours=%s "
                "leave_deduction_status=%s remaining_after_all=%s carry_out_expected=%s",
                slip.id,
                lateness,
                carry_in,
                weighted_total,
                consume_wallet_equiv,
                consumed_current_equiv,
                (consume_wallet_equiv + consumed_current_equiv),
                payout_hours,
                leave_deduction_status,
                remaining,
                carry_out_equiv,
            )

            slip.write({
                'lateness_reconciled': True,
                'lateness_reconcile_snapshot': json.dumps(snapshot),
                'lateness_reconcile_leave_id': created_leave.id or False,
                'ot_wallet_carry_in_equiv': carry_in,
                'ot_wallet_earned_equiv': weighted_total,
                'ot_wallet_lateness_consumed_equiv': consume_wallet_equiv + consumed_current_equiv,
                'ot_wallet_payout_equiv': payout_hours,
                'ot_wallet_consumed_equiv': consume_wallet_equiv + consumed_current_equiv + payout_hours,
                'ot_wallet_carry_out_equiv': carry_out_equiv,
            })

        self._recompute_ot_wallet_after_payout()
        return True

    def action_reset_lateness_reconciliation(self):
        reset_done = self.browse()
        for slip in self:
            if not slip.lateness_reconciled:
                continue

            payload = {}
            if slip.lateness_reconcile_snapshot:
                try:
                    payload = json.loads(slip.lateness_reconcile_snapshot) or {}
                except Exception:
                    payload = {}

            leave_model = self.env['hr.leave'].sudo()
            leave_ids = set(payload.get('created_leave_ids') or [])
            if slip.lateness_reconcile_leave_id:
                leave_ids.add(slip.lateness_reconcile_leave_id.id)
            generated_leaves = leave_model.search([
                ('employee_id', '=', slip.employee_id.id),
                ('lateness_reconcile_generated', '=', True),
                ('lateness_reconcile_payslip_id', '=', slip.id),
            ])
            leaves = (leave_model.browse(list(leave_ids)).exists() | generated_leaves).sorted('id')
            _logger.info(
                "[LatenessReset] cleanup_leaves slip_id=%s leave_ids=%s",
                slip.id, leaves.ids
            )
            for leave in leaves:
                if leave.state in ('confirm', 'validate1', 'validate', 'draft') and hasattr(leave, 'action_refuse'):
                    try:
                        leave.action_refuse()
                    except Exception as err:
                        _logger.warning(
                            "[LatenessReset] refuse_leave_failed slip_id=%s leave_id=%s state=%s error=%s",
                            slip.id, leave.id, leave.state, err
                        )
            # Remove generated leaves from this reconciliation flow so they cannot
            # affect overlap checks or confuse users after reset.
            to_unlink = leaves.filtered(
                lambda l: l.lateness_reconcile_generated
                and l.lateness_reconcile_payslip_id.id == slip.id
                and l.state in ('cancel', 'refuse', 'draft')
            )
            if to_unlink:
                try:
                    to_unlink.unlink()
                except Exception as err:
                    _logger.warning(
                        "[LatenessReset] unlink_generated_leaves_failed slip_id=%s leave_ids=%s error=%s",
                        slip.id, to_unlink.ids, err
                    )

            slip._restore_lateness_snapshot()

            slip.write({
                'lateness_reconciled': False,
                'lateness_reconcile_snapshot': False,
                'lateness_reconcile_leave_id': False,
                'ot_wallet_carry_in_equiv': 0.0,
                'ot_wallet_earned_equiv': 0.0,
                'ot_wallet_lateness_consumed_equiv': 0.0,
                'ot_wallet_payout_equiv': 0.0,
                'ot_wallet_consumed_equiv': 0.0,
                'ot_wallet_carry_out_equiv': 0.0,
            })
            reset_done |= slip

        if reset_done:
            reset_done.action_rebuild_ot_wallet()
        return True

    def compute_sheet(self):
        self._assert_ot_payout_snapshot_integrity()
        self._recompute_ot_wallet_after_payout()
        return super().compute_sheet()


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    annual_leave_balance_hours = fields.Float(
        string='Annual Leave Balance (hrs)',
        compute='_compute_annual_leave_balance_hours',
        store=False,
        help='Latest remaining lateness value (REMLATE) from the employee payslips.',
    )
    has_non_cancelled_payslip = fields.Boolean(
        compute='_compute_has_non_cancelled_payslip',
        store=False,
        help='Technical field used to control extra-hours deduction button visibility.',
    )

    def _compute_annual_leave_balance_hours(self):
        Payslip = self.env['hr.payslip']
        for employee in self:
            employee.annual_leave_balance_hours = 0.0
            slip = Payslip.search(
                [('employee_id', '=', employee.id)],
                order='date_to desc, id desc',
                limit=1,
            )
            if not slip:
                continue
            remlate_input = slip.input_line_ids.filtered(lambda l: (l.code or '').strip() == 'REMLATE')
            employee.annual_leave_balance_hours = sum(remlate_input.mapped('amount')) if remlate_input else 0.0

    def _compute_has_non_cancelled_payslip(self):
        payslip_counts = dict(
            self.env['hr.payslip']._read_group(
                domain=[
                    ('employee_id', 'in', self.ids),
                    ('state', '!=', 'cancel'),
                ],
                groupby=['employee_id'],
                aggregates=['id:count'],
            )
        )
        for employee in self:
            employee.has_non_cancelled_payslip = bool(employee.id and payslip_counts.get(employee, 0))

    @api.depends('overtime_ids.manual_duration', 'overtime_ids', 'overtime_ids.status')
    def _compute_total_overtime(self):
        """Use latest payslip OT balance as source of truth for extra-hours availability."""
        Payslip = self.env['hr.payslip']
        mapped_validated_overtimes = dict(
            self.env['hr.attendance.overtime.line']._read_group(
                domain=[
                    ('status', '=', 'approved'),
                    ('employee_id', 'in', self.ids),
                ],
                groupby=['employee_id'],
                aggregates=['manual_duration:sum'],
            )
        )
        for employee in self:
            attendance_overtime = mapped_validated_overtimes.get(employee, 0.0) or 0.0
            payslip_balance = 0.0
            if not employee.id:
                employee.total_overtime = attendance_overtime
                continue
            last_payslip = Payslip.search(
                [
                    ('employee_id', '=', employee.id),
                    ('state', '!=', 'cancel'),
                ],
                order='date_to desc, id desc',
                limit=1,
            )
            if last_payslip:
                payslip_balance = last_payslip._get_ot_balance_after_value() or 0.0
                employee.total_overtime = payslip_balance
            else:
                # Fallback only when employee has no payslip yet.
                employee.total_overtime = attendance_overtime
            _logger.info(
                "[OTWallet] employee_total_overtime employee_id=%s employee=%s attendance_overtime=%s "
                "last_payslip_id=%s last_payslip_name=%s last_payslip_state=%s last_payslip_period=%s..%s "
                "payslip_balance=%s total_overtime=%s",
                employee.id,
                employee.display_name,
                attendance_overtime,
                last_payslip.id if last_payslip else False,
                last_payslip.display_name if last_payslip else False,
                last_payslip.state if last_payslip else False,
                last_payslip.date_from if last_payslip else False,
                last_payslip.date_to if last_payslip else False,
                payslip_balance,
                employee.total_overtime,
            )

    def get_overtime_data_by_employee(self):
        """Align Attendance balance widget with OT wallet balance used in payroll."""
        overtime_data = super().get_overtime_data_by_employee()
        deductible_by_employee = self.env['hr.leave']._get_deductible_employee_overtime(self)
        for employee in self:
            data = overtime_data.setdefault(employee.id, {
                "compensable_overtime": 0.0,
                "not_compensable_overtime": 0.0,
                "unspent_compensable_overtime": 0.0,
            })
            data["unspent_compensable_overtime"] = max(deductible_by_employee[employee], 0.0)
            _logger.info(
                "[OTWallet] attendance_widget_overtime employee_id=%s employee=%s compensable=%s not_compensable=%s unspent=%s",
                employee.id,
                employee.display_name,
                data.get("compensable_overtime", 0.0),
                data.get("not_compensable_overtime", 0.0),
                data.get("unspent_compensable_overtime", 0.0),
            )
        return overtime_data

    def _get_default_ot_conversion_payslip(self):
        self.ensure_one()
        payslip = self.env['hr.payslip'].search([
            ('employee_id', '=', self.id),
            ('state', '=', 'draft'),
            ('state', '!=', 'cancel'),
        ], order='date_to desc, id desc', limit=1)
        if not payslip:
            payslip = self.env['hr.payslip'].search([
                ('employee_id', '=', self.id),
                ('state', '!=', 'cancel'),
            ], order='date_to desc, id desc', limit=1)
        return payslip

class HrLeave(models.Model):
    _inherit = 'hr.leave'

    lateness_reconcile_generated = fields.Boolean(
        string='From Lateness Reconciliation',
        default=False,
        copy=False,
        readonly=True,
        index=True,
    )
    lateness_reconcile_reason = fields.Char(
        string='Lateness Source',
        copy=False,
        readonly=True,
    )
    lateness_reconcile_payslip_id = fields.Many2one(
        'hr.payslip',
        string='Lateness Payslip',
        copy=False,
        readonly=True,
        index=True,
    )

    @api.model
    def _get_deductible_employee_overtime(self, employees):
        """Use OT wallet balance from latest payslip as deductible overtime source."""
        diff_by_employee = defaultdict(lambda: 0.0)
        Payslip = self.env['hr.payslip'].sudo()
        for employee in employees:
            last_payslip = Payslip.search(
                [
                    ('employee_id', '=', employee.id),
                    ('state', '!=', 'cancel'),
                ],
                order='date_to desc, id desc',
                limit=1,
            )
            if not last_payslip:
                _logger.info(
                    "[OTWallet] deductible_overtime employee_id=%s employee=%s last_payslip_id=False result=0.0",
                    employee.id,
                    employee.display_name,
                )
                continue
            deductible = last_payslip._get_ot_balance_after_value() or 0.0
            diff_by_employee[employee] = deductible
            _logger.info(
                "[OTWallet] deductible_overtime employee_id=%s employee=%s last_payslip_id=%s "
                "last_payslip_name=%s last_payslip_state=%s last_payslip_period=%s..%s deductible=%s",
                employee.id,
                employee.display_name,
                last_payslip.id,
                last_payslip.display_name,
                last_payslip.state,
                last_payslip.date_from,
                last_payslip.date_to,
                deductible,
            )
        return diff_by_employee


class HrPayslipInputType(models.Model):
    _inherit = 'hr.payslip.input.type'

    is_ot_payout = fields.Boolean(
        string='OT Wallet Payout',
        help='When enabled, this input uses Hours x (Employee Wage / 240) and deducts from OT Wallet.',
    )
    is_ot_leave_conversion = fields.Boolean(
        string='OT to Leave Conversion',
        help='When enabled, this input deducts OT wallet hours and is used to convert overtime to leave allocation.',
    )


class HrPayslipInput(models.Model):
    _inherit = 'hr.payslip.input'

    is_ot_payout = fields.Boolean(related='input_type_id.is_ot_payout', store=False, readonly=True)
    is_ot_leave_conversion = fields.Boolean(
        related='input_type_id.is_ot_leave_conversion',
        store=False,
        readonly=True,
    )
    hours = fields.Float(string='Hours', digits='Payroll Rate')

    @api.onchange('input_type_id', 'hours', 'payslip_id')
    def _onchange_ot_payout_amount(self):
        for line in self:
            if line.is_ot_payout and line.payslip_id:
                line.amount = (line.hours or 0.0) * line.payslip_id._get_hourly_rate_for_ot_payout()

    def _prepare_ot_payout_amount_vals(self, vals, current_input=None):
        vals = dict(vals)
        if 'input_type_id' not in vals and 'hours' not in vals:
            return vals
        input_type_id = vals.get('input_type_id') or (current_input.input_type_id.id if current_input else False)
        payslip_id = vals.get('payslip_id') or (current_input.payslip_id.id if current_input else False)
        if not input_type_id or not payslip_id:
            return vals
        input_type = self.env['hr.payslip.input.type'].browse(input_type_id)
        if input_type.is_ot_payout:
            payslip = self.env['hr.payslip'].browse(payslip_id)
            hours = vals.get('hours', current_input.hours if current_input else 0.0) or 0.0
            vals['amount'] = hours * payslip._get_hourly_rate_for_ot_payout()
        elif input_type.is_ot_leave_conversion:
            vals['amount'] = 0.0
        return vals

    @api.model
    def _is_ot_payout_from_vals(self, vals, current_input=None):
        input_type_id = vals.get('input_type_id') or (current_input.input_type_id.id if current_input else False)
        if not input_type_id:
            return False
        return bool(self.env['hr.payslip.input.type'].browse(input_type_id).is_ot_payout)

    @api.model
    def _is_ot_wallet_deduction_from_vals(self, vals, current_input=None):
        input_type_id = vals.get('input_type_id') or (current_input.input_type_id.id if current_input else False)
        if not input_type_id:
            return False
        input_type = self.env['hr.payslip.input.type'].browse(input_type_id)
        return bool(input_type.is_ot_payout or input_type.is_ot_leave_conversion)

    @api.model
    def _check_ot_payout_create_lock(self, vals_list):
        return True

    def _check_ot_payout_write_lock(self, vals):
        return True

    def _check_ot_payout_unlink_lock(self):
        return True

    @api.model_create_multi
    def create(self, vals_list):
        self._check_ot_payout_create_lock(vals_list)
        prepared_vals_list = []
        for vals in vals_list:
            prepared_vals_list.append(self._prepare_ot_payout_amount_vals(vals))
        records = super().create(prepared_vals_list)
        records.mapped('payslip_id')._recompute_ot_wallet_after_payout()
        return records

    def write(self, vals):
        self._check_ot_payout_write_lock(vals)
        old_payslips = self.mapped('payslip_id')
        if len(self) == 1:
            res = super().write(self._prepare_ot_payout_amount_vals(vals, current_input=self))
        else:
            res = True
            for rec in self:
                rec_vals = rec._prepare_ot_payout_amount_vals(vals, current_input=rec)
                res = super(HrPayslipInput, rec).write(rec_vals) and res
        (old_payslips | self.mapped('payslip_id'))._recompute_ot_wallet_after_payout()
        return res

    def unlink(self):
        self._check_ot_payout_unlink_lock()
        payslips = self.mapped('payslip_id')
        res = super().unlink()
        payslips._recompute_ot_wallet_after_payout()
        return res


class HrEmployeeOtConvertWizard(models.TransientModel):
    _name = 'hr.employee.ot.convert.wizard'
    _description = 'Convert Employee Overtime to Annual Leave Allocation'

    employee_id = fields.Many2one('hr.employee', required=True, readonly=True)

    payslip_id = fields.Many2one(
        'hr.payslip',
        required=True,
        domain="[('employee_id', '=', employee_id), ('state', '!=', 'cancel')]",
        help='Overtime is taken from this payslip month.',
    )

    overtime_available_hours = fields.Float(
        string='Available Overtime (hrs)',
        compute='_compute_overtime_available_hours',
        readonly=True,
    )

    overtime_to_convert_hours = fields.Float(
        string='Overtime to Convert (hrs)',
        required=True
    )

    annual_leave_type_id = fields.Many2one(
        'hr.leave.type',
        string='Annual Leave Type',
        compute='_compute_annual_leave_type_id',
        readonly=True,
    )

    allocation_date_from = fields.Date(
        string='Allocation Date From',
        required=True,
        default=lambda self: fields.Date.context_today(self),
    )

    allocation_date_to = fields.Date(
        string='Allocation Date To',
        required=True,
        default=lambda self: fields.Date.context_today(self),
    )

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        employee_id = vals.get('employee_id') or self.env.context.get('default_employee_id')
        if employee_id and not vals.get('payslip_id'):
            employee = self.env['hr.employee'].browse(employee_id)
            vals['payslip_id'] = employee._get_default_ot_conversion_payslip().id
        return vals

    @api.depends('payslip_id')
    def _compute_overtime_available_hours(self):
        for wizard in self:
            wizard.overtime_available_hours = 0.0
            if wizard.payslip_id:
                wizard.overtime_available_hours = (
                    wizard.payslip_id._get_ot_wallet_available_before_lateness()
                )

    @api.depends('payslip_id')
    def _compute_annual_leave_type_id(self):
        for wizard in self:
            wizard.annual_leave_type_id = (
                wizard.payslip_id._get_configured_annual_leave_type()
                if wizard.payslip_id else False
            )

    def action_convert(self):
        self.ensure_one()

        _logger.warning("========== OT CONVERSION START ==========")
        _logger.warning("Employee: %s", self.employee_id.name)
        _logger.warning("Payslip: %s", self.payslip_id.display_name)
        _logger.warning("Overtime to convert: %s", self.overtime_to_convert_hours)
        _logger.warning("Date From: %s", self.allocation_date_from)
        _logger.warning("Date To: %s", self.allocation_date_to)

        if not self.employee_id or not self.payslip_id:
            raise ValidationError(_('Employee and payslip are required.'))

        if self.payslip_id.employee_id != self.employee_id:
            raise ValidationError(_('Selected payslip does not belong to this employee.'))

        if self.payslip_id.state == 'cancel':
            raise ValidationError(_('Cannot convert overtime on a cancelled payslip.'))

        if self.overtime_to_convert_hours <= 0:
            raise ValidationError(_('Overtime to convert must be greater than 0.'))

        if self.allocation_date_from > self.allocation_date_to:
            raise ValidationError(_('Date From cannot be after Date To.'))

        available = self.payslip_id._get_ot_wallet_available_before_lateness()
        _logger.warning("Available OT: %s", available)

        if self.overtime_to_convert_hours > available + 1e-6:
            raise ValidationError(_(
                'Entered overtime hours (%(entered).2f) exceed available overtime (%(available).2f).'
            ) % {
                'entered': self.overtime_to_convert_hours,
                'available': available,
            })

        leave_type = self.payslip_id._get_configured_annual_leave_type()

        if not leave_type:
            raise ValidationError(_('Annual Leave Type is not configured.'))

        _logger.warning("Leave Type: %s", leave_type.name)
        _logger.warning("Leave Type request_unit: %s", leave_type.request_unit)

        conversion_input_type = self.payslip_id._get_ot_leave_conversion_input_type()

        conversion_input = self.env['hr.payslip.input'].create({
            'payslip_id': self.payslip_id.id,
            'name': _('OT to Annual Leave Conversion'),
            'input_type_id': conversion_input_type.id,
            'hours': self.overtime_to_convert_hours,
            'amount': 0.0,
        })

        hours_per_day = (
            self.employee_id._get_hours_per_day(self.allocation_date_from)
            or HOURS_PER_DAY
        )

        allocation_vals = {
            'employee_id': self.employee_id.id,
            'holiday_status_id': leave_type.id,
            'allocation_type': 'regular',
            'date_from': self.allocation_date_from,
            'date_to': False,
            'number_of_days': self.overtime_to_convert_hours / hours_per_day,
            'is_ot_conversion': True,
            'ot_conversion_payslip_id': self.payslip_id.id,
            'ot_conversion_input_id': conversion_input.id,
        }

        _logger.warning("Allocation vals BEFORE create: %s", allocation_vals)

        allocation = self.env['hr.leave.allocation'].sudo().create(allocation_vals)

        _logger.warning("Created Allocation ID: %s", allocation.id)
        _logger.warning("Stored number_of_days_display: %s", allocation.number_of_days_display)

        allocation.sudo()._action_validate()

        _logger.warning("After validation number_of_days: %s", allocation.number_of_days)

        self.payslip_id.action_rebuild_ot_wallet()

        _logger.warning("========== OT CONVERSION END ==========")

        return {'type': 'ir.actions.client', 'tag': 'reload'}

