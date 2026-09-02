# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import datetime, time, timedelta
import pytz
from odoo import models, fields, api


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    attendance_break_hours = fields.Float(
        string="Lunch Break Deducted",
        compute="_compute_factory_attendance_metrics",
        store=True,
        help="Break hours deducted (1.0h for Factory/Retail, 0.5h for Head Office)."
    )

    net_worked_hours = fields.Float(
        string="Net Worked Hours",
        compute="_compute_factory_attendance_metrics",
        store=True,
        help="Net worked hours after lunch break deduction."
    )

    daily_undertime_hours = fields.Float(
        string="Daily Lateness (Deduction)",
        compute="_compute_factory_attendance_metrics",
        store=True,
        help="Hours short of daily shift target (deducted after 15m grace period)."
    )

    daily_overtime_hours = fields.Float(
        string="Daily Extra Hours",
        compute="_compute_factory_attendance_metrics",
        store=True,
        help="Hours worked beyond daily shift target (eligible after 45m threshold)."
    )

    daily_variance_hours = fields.Float(
        string="Daily Variance (Net)",
        compute="_compute_factory_attendance_metrics",
        store=True,
        help="Net daily variance: positive for overtime, negative for lateness."
    )

    is_public_holiday = fields.Boolean(
        string="Public Holiday",
        default=False
    )

    def _get_public_holiday_dates_batch(self, min_date, max_date, calendar_id=None):
        """
        Ultra-fast single-query batch loader for all public holidays / global leaves
        covering the date range [min_date, max_date] for specific calendar_id (or global leaves).
        Returns a set of datetime.date objects.
        """
        holiday_dates = set()
        if not min_date or not max_date or "resource.calendar.leaves" not in self.env:
            return holiday_dates

        dt_min = fields.Datetime.to_string(datetime.combine(min_date, time.min))
        dt_max = fields.Datetime.to_string(datetime.combine(max_date, time.max))

        domain = [
            ("resource_id", "=", False),
            ("date_from", "<=", dt_max),
            ("date_to", ">=", dt_min),
        ]
        LeaveModel = self.env["resource.calendar.leaves"]
        if "holiday_id" in LeaveModel._fields:
            domain.append(("holiday_id", "=", False))
        if calendar_id:
            domain += ["|", ("calendar_id", "=", False), ("calendar_id", "=", calendar_id)]

        leaves = LeaveModel.sudo().search(domain)

        tz_name = self.env.company.resource_calendar_id.tz or self.env.user.tz or 'Asia/Amman'
        try:
            user_tz = pytz.timezone(tz_name)
        except Exception:
            user_tz = pytz.timezone('Asia/Amman')

        for lve in leaves:
            if not lve.date_from or not lve.date_to:
                continue
            df_utc = lve.date_from.replace(tzinfo=pytz.utc) if lve.date_from.tzinfo is None else lve.date_from
            dt_utc = lve.date_to.replace(tzinfo=pytz.utc) if lve.date_to.tzinfo is None else lve.date_to
            d_from = df_utc.astimezone(user_tz).date()
            d_to = dt_utc.astimezone(user_tz).date()
            curr = d_from
            while curr <= d_to:
                if min_date <= curr <= max_date:
                    holiday_dates.add(curr)
                curr += timedelta(days=1)

        return holiday_dates

    @api.depends('worked_hours', 'employee_id')
    def _compute_factory_attendance_metrics(self):
        if not getattr(self.env.registry, 'ready', True) or self.env.context.get('install_mode') or self.env.context.get('module_installation') or self.env.context.get('tracking_disable'):
            self.attendance_break_hours = 0.0
            self.net_worked_hours = 0.0
            self.daily_undertime_hours = 0.0
            self.daily_overtime_hours = 0.0
            self.daily_variance_hours = 0.0
            self.is_public_holiday = False
            return

        invalid_atts = self.filtered(lambda a: not a.check_in or not a.employee_id or not a.worked_hours)
        if invalid_atts:
            invalid_atts.attendance_break_hours = 0.0
            invalid_atts.net_worked_hours = 0.0
            invalid_atts.daily_undertime_hours = 0.0
            invalid_atts.daily_overtime_hours = 0.0
            invalid_atts.daily_variance_hours = 0.0
            invalid_atts.is_public_holiday = False

        valid_atts = self - invalid_atts
        if not valid_atts:
            return

        cutoff_date = fields.Date.today() - timedelta(days=60)
        recent_atts = valid_atts.filtered(lambda a: a.check_in.date() >= cutoff_date)
        old_atts = valid_atts - recent_atts

        if old_atts:
            old_atts.daily_undertime_hours = 0.0
            old_atts.daily_overtime_hours = 0.0
            old_atts.daily_variance_hours = 0.0
            old_atts.is_public_holiday = False
            for attendance in old_atts:
                raw_hrs = attendance.worked_hours or 0.0
                b_hrs = 1.0 if raw_hrs >= 6.0 else 0.0
                attendance.attendance_break_hours = b_hrs
                attendance.net_worked_hours = max(0.0, raw_hrs - b_hrs)

        if not recent_atts:
            return

        active_dates = [a.check_in.date() for a in recent_atts]
        min_d, max_d = min(active_dates), max(active_dates)

        holidays_by_cal = {}
        emp_cache = {}

        for attendance in recent_atts:
            emp = attendance.employee_id
            emp_id = emp.id
            cal_id = emp.resource_calendar_id.id if emp.resource_calendar_id else False

            if cal_id not in holidays_by_cal:
                holidays_by_cal[cal_id] = self._get_public_holiday_dates_batch(min_d, max_d, calendar_id=cal_id)
            public_holiday_dates = holidays_by_cal[cal_id]

        for attendance in recent_atts:
            emp = attendance.employee_id
            emp_id = emp.id
            if emp_id not in emp_cache:
                emp_cache[emp_id] = {
                    'break_hrs': emp._get_lunch_break_duration(),
                    'is_manager': emp.is_manager_exempt(),
                }
            emp_info = emp_cache[emp_id]

            raw_hrs = attendance.worked_hours or 0.0
            break_hrs = emp_info['break_hrs']

            if raw_hrs >= 6.0:
                net_hrs = max(0.0, raw_hrs - break_hrs)
                deducted_break = break_hrs
            elif raw_hrs > 4.0:
                deducted_break = break_hrs / 2.0
                net_hrs = max(0.0, raw_hrs - deducted_break)
            else:
                deducted_break = 0.0
                net_hrs = raw_hrs

            attendance.attendance_break_hours = deducted_break
            attendance.net_worked_hours = net_hrs

            if emp_info['is_manager']:
                attendance.daily_overtime_hours = 0.0
                attendance.daily_undertime_hours = 0.0
                attendance.daily_variance_hours = 0.0
                attendance.is_public_holiday = False
                continue

            target_date = attendance.check_in.date()
            is_holiday = target_date in public_holiday_dates
            attendance.is_public_holiday = is_holiday

            if is_holiday:
                attendance.daily_overtime_hours = net_hrs
                attendance.daily_undertime_hours = 0.0
                attendance.daily_variance_hours = net_hrs
                continue

            standard_target = 8.0
            min_ot_threshold = 0.75  # 45 minutes
            min_lateness_threshold = 0.25  # 15 minutes

            cal = emp.resource_calendar_id or self.env.company.resource_calendar_id
            tz_name = emp.tz or (cal.tz if cal else False) or self.env.user.tz or 'Asia/Amman'
            try:
                emp_tz = pytz.timezone(tz_name)
            except Exception:
                emp_tz = pytz.timezone('Asia/Amman')

            check_in_local = attendance.check_in.astimezone(emp_tz)
            actual_in_hour = check_in_local.hour + (check_in_local.minute / 60.0)

            actual_out_hour = 0.0
            if attendance.check_out:
                check_out_local = attendance.check_out.astimezone(emp_tz)
                actual_out_hour = check_out_local.hour + (check_out_local.minute / 60.0)

            dow = str(check_in_local.weekday())
            day_cal = cal.attendance_ids.filtered(lambda a: a.dayofweek == dow) if cal else False

            is_flexible = bool(
                getattr(cal, 'flexible_hours', False) 
                or getattr(cal, 'flexible', False) 
                or getattr(emp, 'flexible_hours', False)
                or not day_cal
            )

            if is_flexible:
                # Flexible Schedule Rule: Net Worked Hours vs Daily Target (8.0h)
                target = getattr(cal, 'hours_per_day', 8.0) or 8.0
                excess = net_hrs - target

                if excess >= min_ot_threshold:
                    overtime = round(excess, 2)
                    undertime = 0.0
                elif excess < -min_lateness_threshold:
                    overtime = 0.0
                    undertime = round(abs(excess), 2)
                else:
                    overtime = 0.0
                    undertime = 0.0
            else:
                # Fixed Shift Rule: Check-In vs Shift Start & Overtime from Net Worked Hours
                sched_start = min(day_cal.mapped('hour_from'))

                # Lateness (Check-In delay vs Scheduled Start)
                late_delay = max(0.0, actual_in_hour - sched_start)
                undertime = round(late_delay, 2) if late_delay >= min_lateness_threshold else 0.0

                # Overtime: Net Worked Hours minus Daily Target (8.0h)
                excess = net_hrs - standard_target
                if excess >= min_ot_threshold:
                    overtime = round(excess, 2)
                else:
                    overtime = 0.0

            attendance.daily_undertime_hours = undertime
            attendance.daily_overtime_hours = overtime
            attendance.daily_variance_hours = round(overtime - undertime, 2)

    @api.depends('daily_overtime_hours', 'employee_id')
    def _compute_overtime_hours(self):
        """High-performance in-memory direct assignment (0 DB queries per row)."""
        for attendance in self:
            if attendance.employee_id and attendance.employee_id.is_manager_exempt():
                attendance.overtime_hours = 0.0
            else:
                attendance.overtime_hours = attendance.daily_overtime_hours or 0.0

    @api.depends('daily_overtime_hours')
    def _compute_eligible_overtime(self):
        """Instant eligibility flag based on Daily Extra Hours."""
        for attendance in self:
            attendance.eligible_overtime = bool(attendance.daily_overtime_hours >= 0.75)

    def action_approve_factory_overtime(self):
        """
        Explicit HR Action to validate and approve daily overtime for factory attendance.
        Sets overtime_status to 'approved' and updates validated_overtime_hours from daily_overtime_hours.
        """
        for att in self:
            att_ot = att.daily_overtime_hours if att.daily_overtime_hours >= 0.75 else 0.0
            if att_ot < 0.75:
                att.sudo().write({'overtime_status': 'refused', 'validated_overtime_hours': 0.0})
                if hasattr(att, 'linked_overtime_ids') and att.linked_overtime_ids:
                    att.linked_overtime_ids.sudo().write({'status': 'refused', 'duration': 0.0})
                continue

            vals = {}
            if hasattr(att, 'overtime_status'):
                vals['overtime_status'] = 'approved'
            if hasattr(att, 'validated_overtime_hours'):
                vals['validated_overtime_hours'] = att_ot
            if vals:
                att.sudo().write(vals)

            if hasattr(att, 'linked_overtime_ids') and att.linked_overtime_ids:
                att.linked_overtime_ids.sudo().write({
                    'status': 'approved',
                    'duration': att_ot,
                    'manual_duration': att_ot,
                })
            elif 'hr.attendance.overtime.line' in self.env:
                att_date = att.check_in.date() if att.check_in else None
                if att_date and att.employee_id:
                    ot_lines = self.env['hr.attendance.overtime.line'].sudo().search([
                        ('employee_id', '=', att.employee_id.id),
                        ('date', '=', att_date)
                    ])
                    if ot_lines:
                        ot_lines.write({
                            'status': 'approved',
                            'duration': att_ot,
                            'manual_duration': att_ot,
                        })
                    else:
                        self.env['hr.attendance.overtime.line'].sudo().create({
                            'employee_id': att.employee_id.id,
                            'date': att_date,
                            'duration': att_ot,
                            'manual_duration': att_ot,
                            'status': 'approved',
                            'compensable_as_leave': True,
                        })
        return True

    def action_refuse_factory_overtime(self):
        """
        Explicit HR Action to refuse daily overtime for factory attendance.
        Sets overtime_status to 'refused' and clears validated_overtime_hours.
        """
        for att in self:
            vals = {}
            if hasattr(att, 'overtime_status'):
                vals['overtime_status'] = 'refused'
            if hasattr(att, 'validated_overtime_hours'):
                vals['validated_overtime_hours'] = 0.0
            if vals:
                att.sudo().write(vals)

            if hasattr(att, 'linked_overtime_ids') and att.linked_overtime_ids:
                att.linked_overtime_ids.sudo().write({'status': 'refused', 'duration': 0.0})
            elif 'hr.attendance.overtime.line' in self.env:
                att_date = att.check_in.date() if att.check_in else None
                if att_date and att.employee_id:
                    ot_lines = self.env['hr.attendance.overtime.line'].sudo().search([
                        ('employee_id', '=', att.employee_id.id),
                        ('date', '=', att_date)
                    ])
                    if ot_lines:
                        ot_lines.write({'status': 'refused', 'duration': 0.0})
        return True

    @api.onchange('overtime_status')
    def _onchange_overtime_status(self):
        for att in self:
            if att.overtime_status == 'approved':
                att.validated_overtime_hours = att.daily_overtime_hours if att.daily_overtime_hours >= 0.75 else 0.0
            elif att.overtime_status == 'refused':
                att.validated_overtime_hours = 0.0

    def write(self, vals):
        if vals.get('overtime_status') == 'approved' and 'validated_overtime_hours' not in vals:
            for att in self:
                att_ot = att.daily_overtime_hours if att.daily_overtime_hours >= 0.75 else 0.0
                vals['validated_overtime_hours'] = att_ot
        elif vals.get('overtime_status') == 'refused' and 'validated_overtime_hours' not in vals:
            vals['validated_overtime_hours'] = 0.0
        return super(HrAttendance, self.with_context(bypass_work_entry_check=True)).write(vals)

    def _check_weekly_overtime_eligibility(self):
        """Allow approval if attendance has valid positive extra hours."""
        factory_atts = self.filtered(lambda a: a.daily_overtime_hours >= 0.75)
        other_atts = self - factory_atts
        if other_atts and hasattr(super(), '_check_weekly_overtime_eligibility'):
            try:
                super(HrAttendance, other_atts)._check_weekly_overtime_eligibility()
            except Exception:
                pass

    def action_approve_overtime(self):
        """Standard Odoo action_approve_overtime override."""
        for att in self:
            att_ot = att.daily_overtime_hours if att.daily_overtime_hours >= 0.75 else 0.0
            if hasattr(att, 'validated_overtime_hours'):
                att.validated_overtime_hours = att_ot
        if hasattr(super(), 'action_approve_overtime'):
            try:
                res = super().action_approve_overtime()
            except Exception:
                res = self.action_approve_factory_overtime()
        else:
            res = self.action_approve_factory_overtime()
        for att in self:
            att_ot = att.daily_overtime_hours if att.daily_overtime_hours >= 0.75 else 0.0
            if hasattr(att, 'validated_overtime_hours'):
                att.sudo().write({
                    'validated_overtime_hours': att_ot,
                    'overtime_status': 'approved' if att_ot >= 0.75 else 'refused'
                })
        return res

    def _update_overtime(self, attendance_domain=None):
        """
        Batch-optimized overtime generator: Pre-fetches all overtime lines
        in 1 bulk query and ensures overtime lines match daily_overtime_hours.
        """
        res = super()._update_overtime(attendance_domain=attendance_domain)
        cutoff_date = fields.Date.today() - timedelta(days=60)
        valid_atts = self.filtered(lambda a: a.employee_id and a.worked_hours and a.check_in and a.check_in.date() >= cutoff_date)
        if not valid_atts:
            return res

        emp_ids = valid_atts.mapped('employee_id').ids
        att_dates = list(set(a.check_in.date() for a in valid_atts))

        ot_by_key = {}
        if 'hr.attendance.overtime' in self.env:
            ot_recs = self.env['hr.attendance.overtime'].sudo().search([
                ('employee_id', 'in', emp_ids),
                ('date', 'in', att_dates)
            ])
            ot_by_key = {(r.employee_id.id, r.date): r for r in ot_recs}

        ot_lines_by_key = {}
        if 'hr.attendance.overtime.line' in self.env:
            ot_lines = self.env['hr.attendance.overtime.line'].sudo().search([
                ('employee_id', 'in', emp_ids),
                ('date', 'in', att_dates)
            ])
            ot_lines_by_key = {(l.employee_id.id, l.date): l for l in ot_lines}

        to_zero_ot = self.env['hr.attendance.overtime'] if 'hr.attendance.overtime' in self.env else False
        to_zero_lines = self.env['hr.attendance.overtime.line'] if 'hr.attendance.overtime.line' in self.env else False
        excess_writes = defaultdict(list)

        for att in valid_atts:
            try:
                raw_hrs = att.worked_hours
                break_hrs = att.employee_id._get_lunch_break_duration()

                if raw_hrs >= 6.0:
                    net_hrs = max(0.0, raw_hrs - break_hrs)
                elif raw_hrs > 4.0:
                    net_hrs = max(0.0, raw_hrs - (break_hrs / 2.0))
                else:
                    net_hrs = raw_hrs

                target_date = att.check_in.date() if att.check_in else False
                expected_hrs = 8.0
                standard_target = expected_hrs if expected_hrs > 0 else 8.0
                excess = net_hrs - standard_target
                min_ot_threshold = 0.75

                att_date = att.check_in.date()
                key = (att.employee_id.id, att_date)

                ot_rec = ot_by_key.get(key)
                ot_line = ot_lines_by_key.get(key)

                if excess < min_ot_threshold:
                    if ot_rec:
                        to_zero_ot |= ot_rec
                    if ot_line:
                        to_zero_lines |= ot_line
                else:
                    if ot_rec:
                        excess_writes[excess].append(ot_rec.id)
            except Exception:
                pass

        if to_zero_ot:
            to_zero_ot.sudo().write({'duration': 0.0})
        if to_zero_lines:
            to_zero_lines.sudo().write({'duration': 0.0, 'manual_duration': 0.0})
        if 'hr.attendance.overtime' in self.env:
            for exc_val, rec_ids in excess_writes.items():
                self.env['hr.attendance.overtime'].browse(rec_ids).sudo().write({'duration': exc_val})
        return res
