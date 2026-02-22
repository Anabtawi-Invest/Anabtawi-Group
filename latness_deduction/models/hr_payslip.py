import logging
import json

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
    ot_wallet_total_before_deduction_equiv = fields.Float(
        string='OT balance',
        compute='_compute_ot_wallet_total_before_deduction_equiv',
        store=True,
        readonly=True,
        copy=False,
    )
    ot_wallet_consumed_equiv = fields.Float(copy=False, readonly=True, default=0.0)
    ot_wallet_carry_out_equiv = fields.Float(copy=False, readonly=True, default=0.0)

    def _build_lateness_snapshot(self):
        """Capture original worked days and REMLATE before reconciliation."""
        self.ensure_one()
        remlate_input = self.input_line_ids.filtered(lambda l: (l.code or '').strip() == 'REMLATE')[:1]
        return {
            'worked_days_hours': {str(line.id): (line.number_of_hours or 0.0) for line in self.worked_days_line_ids},
            'remlate_amount': remlate_input.amount if remlate_input else None,
            'ot_wallet_carry_in_equiv': self.ot_wallet_carry_in_equiv,
            'ot_wallet_earned_equiv': self.ot_wallet_earned_equiv,
            'ot_wallet_consumed_equiv': self.ot_wallet_consumed_equiv,
            'ot_wallet_carry_out_equiv': self.ot_wallet_carry_out_equiv,
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
            'ot_wallet_consumed_equiv': payload.get('ot_wallet_consumed_equiv', 0.0),
            'ot_wallet_carry_out_equiv': payload.get('ot_wallet_carry_out_equiv', 0.0),
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
        """Build a single-day leave slot in payslip period for the required hours."""
        self.ensure_one()
        if remaining_hours <= 0 or not self.employee_id or not leave_type:
            return False
        leave_day = self.date_to or self.date_from or fields.Date.today()
        leave_preview = self.env['hr.leave'].new({
            'employee_id': self.employee_id.id,
            'holiday_status_id': leave_type.id,
            'request_date_from': leave_day,
            'request_date_to': leave_day,
            'request_unit_hours': True,
        })
        hour_from, hour_to = leave_preview._get_hour_from_to(leave_day, leave_day)
        if hour_to <= hour_from:
            return False
        if (hour_to - hour_from) < remaining_hours:
            return False
        return leave_day, hour_from, hour_from + remaining_hours

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
            consumed = min(lateness, carry + earned)
            carry_before = carry
            carry = max(carry + earned - consumed, 0.0)
            _logger.info(
                "[OTWallet] previous slip_id=%s date_to=%s lateness=%s otw=%s otr=%s pho=%s earned_equiv=%s carry_in=%s consumed=%s carry_out=%s",
                slip.id,
                slip.date_to,
                lateness,
                buckets.get('OTW', 0.0),
                buckets.get('OTR', 0.0),
                buckets.get('PHO', 0.0),
                earned,
                carry_before,
                consumed,
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
                consumed = min(lateness, carry_in + earned)
                carry_out = max(carry_in + earned - consumed, 0.0)
                slip.write({
                    'ot_wallet_carry_in_equiv': carry_in,
                    'ot_wallet_earned_equiv': earned,
                    'ot_wallet_consumed_equiv': consumed,
                    'ot_wallet_carry_out_equiv': carry_out,
                })
                _logger.info(
                    "[OTWallet] rebuild slip_id=%s date_to=%s lateness=%s otw=%s otr=%s pho=%s carry_in=%s earned=%s consumed=%s carry_out=%s",
                    slip.id,
                    slip.date_to,
                    lateness,
                    buckets.get('OTW', 0.0),
                    buckets.get('OTR', 0.0),
                    buckets.get('PHO', 0.0),
                    carry_in,
                    earned,
                    consumed,
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
                rem = max(lateness - (carry_in + slip._get_weighted_ot_hours(buckets)), 0.0)
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
        for slip in self:
            if slip.lateness_reconciled:
                raise UserError(_('Lateness reconciliation already applied. Use "Reset Reconciliation" first.'))

            snapshot = slip._build_lateness_snapshot()
            remlate_input_type = slip._get_remlate_input_type()
            lateness, buckets = slip._get_worked_day_hours_by_code()
            remaining = lateness
            created_leave = self.env['hr.leave']
            carry_in = slip._get_previous_ot_wallet_carry_out()
            weighted_total = slip._get_weighted_ot_hours(buckets)
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

            # 1) consume previously carried OT wallet first (equivalent hours).
            consume_wallet_equiv = min(carry_in, remaining)
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
                consume_equiv = min(available_equiv, remaining)
                consume_raw = consume_equiv / multiplier if multiplier else 0.0
                _logger.info(
                    "[LatenessReconcile] consume_ot slip_id=%s code=%s available_raw=%s available_equiv=%s consume_equiv=%s consume_raw=%s remaining_before=%s",
                    slip.id, code, available_raw, available_equiv, consume_equiv, consume_raw, remaining
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
                leave_type = slip._get_configured_annual_leave_type()
                if not leave_type:
                    raise UserError(_(
                        'Annual Leave Type for lateness coverage is not configured.\n'
                        'Go to Payroll Settings > Lateness Coverage and set Annual Leave Type for Lateness.'
                    ))

                # If allocation is required but unavailable, keep remaining for payroll deduction (REMLATE)
                # instead of crashing with "There is no valid allocation to cover that request."
                has_valid_allocation = leave_type.with_context(employee_id=slip.employee_id.id).has_valid_allocation
                _logger.info(
                    "[LatenessReconcile] leave_check slip_id=%s leave_type_id=%s requires_allocation=%s has_valid_allocation=%s remaining=%s",
                    slip.id, leave_type.id, leave_type.requires_allocation, has_valid_allocation, remaining
                )
                if not (leave_type.requires_allocation and not has_valid_allocation):
                    try:
                        slip_ref = slip.name or _('Payslip')
                        leave_slot = slip._get_valid_leave_slot(remaining, leave_type)
                        if not leave_slot:
                            _logger.warning(
                                "[LatenessReconcile] no_valid_leave_slot slip_id=%s remaining=%s; fallback to REMLATE",
                                slip.id, remaining
                            )
                            raise ValidationError(_("No valid working slot found for this leave request."))
                        leave_day, start_hour, end_hour = leave_slot

                        overlapping_leave = Leave.sudo().search([
                            ('employee_id', '=', slip.employee_id.id),
                            ('state', 'in', ['confirm', 'validate1', 'validate']),
                            ('request_date_from', '<=', leave_day),
                            ('request_date_to', '>=', leave_day),
                        ], limit=1)
                        if overlapping_leave:
                            _logger.warning(
                                "[LatenessReconcile] overlapping_leave slip_id=%s leave_day=%s existing_leave_id=%s; fallback to REMLATE",
                                slip.id, leave_day, overlapping_leave.id
                            )
                            raise ValidationError(_("Overlapping time off exists for this day."))

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
                        created_leave = leave
                        _logger.info(
                            "[LatenessReconcile] leave_created slip_id=%s leave_id=%s number_of_hours=%s number_of_days=%s state=%s",
                            slip.id, leave.id, leave.number_of_hours, leave.number_of_days, leave.state
                        )
                        remaining = 0.0
                    except (ValidationError, UserError):
                        _logger.exception(
                            "[LatenessReconcile] leave_create_failed slip_id=%s remaining=%s; fallback to REMLATE",
                            slip.id, remaining
                        )
                        pass

            # 3) Store remaining lateness for payroll deduction rule (input line)
            # Always keep input line consistent (even if 0)
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
            slip.write({
                'lateness_reconciled': True,
                'lateness_reconcile_snapshot': json.dumps(snapshot),
                'lateness_reconcile_leave_id': created_leave.id or False,
                'ot_wallet_carry_in_equiv': carry_in,
                'ot_wallet_earned_equiv': weighted_total,
                'ot_wallet_consumed_equiv': consume_wallet_equiv + consumed_current_equiv,
                'ot_wallet_carry_out_equiv': max(carry_in + weighted_total - (consume_wallet_equiv + consumed_current_equiv), 0.0),
            })
            _logger.info(
                "[LatenessReconcile] end slip_id=%s final_remaining=%s wallet_in=%s wallet_earned=%s wallet_consumed=%s wallet_out=%s remlate_input_exists=%s",
                slip.id,
                remaining,
                carry_in,
                weighted_total,
                consume_wallet_equiv + consumed_current_equiv,
                max(carry_in + weighted_total - (consume_wallet_equiv + consumed_current_equiv), 0.0),
                bool(inp)
            )
        return True

    def action_reset_lateness_reconciliation(self):
        for slip in self:
            if not slip.lateness_reconciled:
                continue

            slip._restore_lateness_snapshot()

            leave = slip.lateness_reconcile_leave_id.sudo().exists()
            if leave and leave.state in ('confirm', 'validate1', 'validate') and hasattr(leave, 'action_refuse'):
                leave.action_refuse()

            slip.write({
                'lateness_reconciled': False,
                'lateness_reconcile_snapshot': False,
                'lateness_reconcile_leave_id': False,
                'ot_wallet_carry_in_equiv': 0.0,
                'ot_wallet_earned_equiv': 0.0,
                'ot_wallet_consumed_equiv': 0.0,
                'ot_wallet_carry_out_equiv': 0.0,
            })
        return True


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    annual_leave_balance_hours = fields.Float(
        string='Annual Leave Balance (hrs)',
        compute='_compute_annual_leave_balance_hours',
        store=False,
        help='Latest remaining lateness value (REMLATE) from the employee payslips.',
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