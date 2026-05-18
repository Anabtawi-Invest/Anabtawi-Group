from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta, time
import pytz
import logging

_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    # Extra fields added to attendance records
    is_auto_checkout = fields.Boolean(
        string='Auto Check-out',
        default=False,
        readonly=True,
        help='Set to True when the system performed automatic check-out.',
    )
    overtime_request_id = fields.Many2one(
        'attendance.overtime.request',
        string='Overtime Request',
        readonly=True,
        help='Linked approved overtime request that enabled this check-in or extended check-out.',
    )
    checkin_note = fields.Char(
        string='Check-in Note',
        readonly=True,
        help='System note explaining check-in validation result.',
    )
    extra_hours = fields.Float(
        string='Extra Hours',
        compute='_compute_extra_hours',
        store=True,
        help='Hours worked beyond the scheduled shift end (without overtime approval).',
    )
    scheduled_check_out = fields.Datetime(
        string='Scheduled Check-out',
        readonly=True,
        help='The expected check-out time based on shift + approved overtime.',
    )

    @api.depends('check_in', 'check_out', 'employee_id')
    def _compute_extra_hours(self):
        for att in self:
            if not att.check_in or not att.check_out or not att.employee_id:
                att.extra_hours = 0.0
                continue

            work_date = att.check_in.date()
            shift_end = self._get_employee_shift_end(att.employee_id, work_date)
            if not shift_end:
                att.extra_hours = 0.0
                continue

            if att.check_out > shift_end:
                delta = att.check_out - shift_end
                # Only count as extra if no overtime was approved
                ot_req = self.env['attendance.overtime.request'].get_approved_overtime_for_employee_date(
                    att.employee_id.id, work_date
                )
                if not ot_req:
                    att.extra_hours = delta.total_seconds() / 3600.0
                else:
                    att.extra_hours = 0.0
            else:
                att.extra_hours = 0.0

    # -------------------------------------------------------------------------
    # Overrides: enforce check-in window on create/write
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        config = self.env['res.config.settings']._get_att_config()
        for vals in vals_list:
            employee_id = vals.get('employee_id')
            if not employee_id:
                continue
            employee = self.env['hr.employee'].browse(employee_id)
            if employee and config.get('enforce_checkin_window', True):
                check_in_dt = vals.get('check_in')
                if isinstance(check_in_dt, str):
                    check_in_dt = fields.Datetime.from_string(check_in_dt)
                if check_in_dt:
                    self._validate_checkin_window(employee, check_in_dt)
                    # Compute and store scheduled checkout
                    scheduled_co = self._compute_scheduled_checkout(employee, check_in_dt)
                    if scheduled_co:
                        vals['scheduled_check_out'] = scheduled_co
        return super().create(vals_list)

    # -------------------------------------------------------------------------
    # Core validation helpers
    # -------------------------------------------------------------------------

    def _validate_checkin_window(self, employee, check_in_dt):
        """
        Raise UserError if check_in_dt falls outside the allowed window.
        Window = [shift_start - tolerance, shift_end + auto_checkout_grace + overtime]
        For re-check-in (same day, second check-in with approved overtime): allowed.
        """
        work_date = check_in_dt.date()
        config = self.env['res.config.settings']._get_att_config()
        tolerance_minutes = config.get('checkin_tolerance_minutes', 30)
        auto_checkout_grace = config.get('auto_checkout_grace_minutes', 15)

        shift_start, shift_end = self._get_employee_shift_window(employee, work_date)

        if not shift_start or not shift_end:
            # No schedule found - allow check-in but log
            _logger.warning(
                'No work schedule found for employee %s on %s. Check-in allowed.',
                employee.name, work_date
            )
            return

        # Convert to UTC for comparison (check_in_dt is already UTC in Odoo)
        allowed_start = shift_start - timedelta(minutes=tolerance_minutes)

        # Check if there's an approved overtime request
        ot_req = self.env['attendance.overtime.request'].get_approved_overtime_for_employee_date(
            employee.id, work_date
        )

        # Check if this is a re-check-in (employee already has a completed attendance today)
        existing_today = self.search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', datetime.combine(work_date, time.min)),
            ('check_in', '<', datetime.combine(work_date + timedelta(days=1), time.min)),
            ('check_out', '!=', False),
        ])

        if existing_today and ot_req:
            # Re-check-in for overtime: window from shift_end (with tolerance) to shift_end + OT hours
            ot_allowed_start = shift_end - timedelta(minutes=tolerance_minutes)
            ot_allowed_end = shift_end + timedelta(hours=ot_req.overtime_hours)
            if not (ot_allowed_start <= check_in_dt <= ot_allowed_end):
                tz = pytz.timezone(employee.tz or 'UTC')
                local_start = pytz.utc.localize(ot_allowed_start).astimezone(tz)
                local_end = pytz.utc.localize(ot_allowed_end).astimezone(tz)
                raise UserError(_(
                    'Re-check-in for overtime is only allowed between %(start)s and %(end)s '
                    '(Overtime approved: %(hours)s hours).',
                    start=local_start.strftime('%H:%M'),
                    end=local_end.strftime('%H:%M'),
                    hours=ot_req.overtime_hours,
                ))
            return

        # Normal first check-in: allowed end is shift_end + grace period
        # If OT is approved, we also extend the window to cover shift_end + OT
        if ot_req:
            allowed_end = shift_end + timedelta(hours=ot_req.overtime_hours)
        else:
            allowed_end = shift_end + timedelta(minutes=auto_checkout_grace)

        if not (allowed_start <= check_in_dt <= allowed_end):
            tz = pytz.timezone(employee.tz or 'UTC')
            local_allowed_start = pytz.utc.localize(allowed_start).astimezone(tz)
            local_shift_start = pytz.utc.localize(shift_start).astimezone(tz)
            local_shift_end = pytz.utc.localize(shift_end).astimezone(tz)

            raise UserError(_(
                'Check-in not allowed at this time for %(employee)s.\n\n'
                'Scheduled shift: %(shift_start)s – %(shift_end)s\n'
                'Earliest allowed check-in: %(allowed_start)s (%(tolerance)d min tolerance)\n\n'
                'If you need to work overtime, please submit an Overtime Request first.',
                employee=employee.name,
                shift_start=local_shift_start.strftime('%H:%M'),
                shift_end=local_shift_end.strftime('%H:%M'),
                allowed_start=local_allowed_start.strftime('%H:%M'),
                tolerance=tolerance_minutes,
            ))

    def _get_employee_shift_window(self, employee, work_date):
        """
        Returns (shift_start_utc, shift_end_utc) for the employee on work_date.
        Checks planning slots first, then work schedule.
        Returns (None, None) if no schedule found.
        """
        tz = pytz.timezone(employee.tz or 'UTC')

        # 1. Check planning slots (for shift-based employees)
        try:
            planning_slots = self.env['planning.slot'].sudo().search([
                ('employee_id', '=', employee.id),
                ('start_datetime', '>=', datetime.combine(work_date, time.min)),
                ('start_datetime', '<', datetime.combine(work_date + timedelta(days=1), time.min)),
                ('state', 'in', ['published', 'confirmed']),
            ], order='start_datetime asc')

            if planning_slots:
                # Use earliest start and latest end of the day's slots
                shift_start = min(s.start_datetime for s in planning_slots)
                shift_end = max(s.end_datetime for s in planning_slots)
                return shift_start, shift_end
        except Exception:
            _logger.debug('Planning module not available or no slots found.')

        # 2. Fall back to resource.calendar (work schedule)
        schedule = employee.resource_calendar_id
        if not schedule:
            return None, None

        day_of_week = work_date.weekday()
        attendances = schedule.attendance_ids.filtered(
            lambda a: int(a.dayofweek) == day_of_week
        )
        if not attendances:
            return None, None

        earliest = min(attendances, key=lambda a: a.hour_from)
        latest = max(attendances, key=lambda a: a.hour_to)

        def hours_to_utc(work_date, hour_float, tz):
            h = int(hour_float)
            m = int((hour_float - h) * 60)
            local_dt = tz.localize(datetime(work_date.year, work_date.month, work_date.day, h, m))
            return local_dt.astimezone(pytz.utc).replace(tzinfo=None)

        shift_start = hours_to_utc(work_date, earliest.hour_from, tz)
        shift_end = hours_to_utc(work_date, latest.hour_to, tz)
        return shift_start, shift_end

    def _get_employee_shift_end(self, employee, work_date):
        """Convenience: return only the shift_end UTC datetime."""
        _, shift_end = self._get_employee_shift_window(employee, work_date)
        return shift_end

    def _compute_scheduled_checkout(self, employee, check_in_dt):
        """
        Return the expected checkout time (UTC) for this attendance record.
        = shift_end + overtime_hours (if approved) else shift_end.
        Auto-checkout fires at scheduled_checkout + grace_minutes.
        """
        work_date = check_in_dt.date()
        _, shift_end = self._get_employee_shift_window(employee, work_date)
        if not shift_end:
            return False

        ot_req = self.env['attendance.overtime.request'].get_approved_overtime_for_employee_date(
            employee.id, work_date
        )
        if ot_req:
            return shift_end + timedelta(hours=ot_req.overtime_hours)
        return shift_end

    # -------------------------------------------------------------------------
    # Auto-checkout cron
    # -------------------------------------------------------------------------

    @api.model
    def _cron_auto_checkout(self):
        """
        Called every minute (or every 5 minutes) by the scheduler.
        For every open attendance (no check_out), check if the auto-checkout
        time has been reached and perform checkout.

        Auto-checkout time = scheduled_check_out + grace_minutes
        If no scheduled_check_out stored, recompute it.
        """
        config = self.env['res.config.settings']._get_att_config()
        if not config.get('auto_checkout_enabled', True):
            return

        grace_minutes = config.get('auto_checkout_grace_minutes', 15)
        now = fields.Datetime.now()

        # Find all open attendances
        open_attendances = self.search([('check_out', '=', False)])

        for att in open_attendances:
            if not att.employee_id or not att.check_in:
                continue

            work_date = att.check_in.date()

            # Get or compute scheduled checkout
            scheduled_co = att.scheduled_check_out
            if not scheduled_co:
                scheduled_co = self._compute_scheduled_checkout(att.employee_id, att.check_in)
                if scheduled_co:
                    att.sudo().write({'scheduled_check_out': scheduled_co})

            if not scheduled_co:
                continue

            # Auto-checkout trigger time
            auto_checkout_at = scheduled_co + timedelta(minutes=grace_minutes)

            if now >= auto_checkout_at:
                _logger.info(
                    'Auto-checkout: employee=%s, check_in=%s, auto_checkout_at=%s',
                    att.employee_id.name, att.check_in, auto_checkout_at
                )
                try:
                    att.sudo().write({
                        'check_out': auto_checkout_at,
                        'is_auto_checkout': True,
                        'checkin_note': _(
                            'Auto check-out performed at %(time)s. '
                            'Scheduled end: %(sched)s.',
                            time=auto_checkout_at.strftime('%H:%M UTC'),
                            sched=scheduled_co.strftime('%H:%M UTC'),
                        ),
                    })
                except Exception as e:
                    _logger.error('Auto-checkout failed for att %s: %s', att.id, e)
