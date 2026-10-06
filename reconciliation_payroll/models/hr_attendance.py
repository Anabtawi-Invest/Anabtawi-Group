# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta
import pytz
from odoo import models, fields, api


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    attendance_break_hours = fields.Float(
        string="Lunch Break Deducted",
        compute="_compute_metrics",
        store=False,
        help="Break hours deducted (1.0h for Factory/Retail, 0.5h for Head Office)."
    )

    net_worked_hours = fields.Float(
        string="Net Worked Hours",
        compute="_compute_metrics",
        store=False,
        help="Net worked hours after lunch break deduction."
    )

    daily_undertime_hours = fields.Float(
        string="Daily Lateness",
        compute="_compute_metrics",
        store=False,
        help="Hours short of daily shift target (deducted after 15m grace period)."
    )

    daily_overtime_hours = fields.Float(
        string="Daily Extra Hours",
        compute="_compute_metrics",
        store=False,
        help="Hours worked beyond daily shift target (eligible after 45m threshold)."
    )

    daily_variance_hours = fields.Float(
        string="Daily Variance",
        compute="_compute_metrics",
        store=False,
        help="Net daily variance: positive for overtime, negative for lateness."
    )

    is_public_holiday = fields.Boolean(
        string="Public Holiday",
        default=False
    )

    def _get_public_holiday_dates_batch(self, min_date, max_date, calendar_id=None):
        """Batch loader for public holidays in date range [min_date, max_date]."""
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
        if calendar_id:
            domain += ["|", ("calendar_id", "=", False), ("calendar_id", "=", calendar_id)]

        leaves = self.env["resource.calendar.leaves"].sudo().search(domain)
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

    @api.depends('worked_hours', 'employee_id', 'check_in', 'check_out')
    def _compute_metrics(self):
        if not getattr(self.env.registry, 'ready', True) or self.env.context.get('install_mode') or self.env.context.get('module_installation'):
            self.attendance_break_hours = 0.0
            self.net_worked_hours = 0.0
            self.daily_undertime_hours = 0.0
            self.daily_overtime_hours = 0.0
            self.daily_variance_hours = 0.0
            self.is_public_holiday = False
            return

        cutoff_date = fields.Date.today() - timedelta(days=60)
        valid_atts = self.filtered(lambda a: a.check_in and a.employee_id and a.worked_hours)
        invalid_atts = self - valid_atts

        if invalid_atts:
            invalid_atts.attendance_break_hours = 0.0
            invalid_atts.net_worked_hours = 0.0
            invalid_atts.daily_undertime_hours = 0.0
            invalid_atts.daily_overtime_hours = 0.0
            invalid_atts.daily_variance_hours = 0.0
            invalid_atts.is_public_holiday = False

        if not valid_atts:
            return

        recent_atts = valid_atts.filtered(lambda a: a.check_in.date() >= cutoff_date)
        old_atts = valid_atts - recent_atts

        for att in old_atts:
            raw_hrs = att.worked_hours or 0.0
            b_hrs = 1.0 if raw_hrs >= 6.0 else (0.5 if raw_hrs > 4.0 else 0.0)
            att.attendance_break_hours = b_hrs
            att.net_worked_hours = max(0.0, raw_hrs - b_hrs)
            att.daily_undertime_hours = 0.0
            att.daily_overtime_hours = 0.0
            att.daily_variance_hours = 0.0
            att.is_public_holiday = False

        if not recent_atts:
            return

        active_dates = [a.check_in.date() for a in recent_atts]
        min_d, max_d = min(active_dates), max(active_dates)
        holidays_by_cal = {}

        for att in recent_atts:
            emp = att.employee_id
            cal = emp.resource_calendar_id or self.env.company.resource_calendar_id
            cal_id = cal.id if cal else False
            if cal_id not in holidays_by_cal:
                holidays_by_cal[cal_id] = self._get_public_holiday_dates_batch(min_d, max_d, calendar_id=cal_id)
            pub_holidays = holidays_by_cal[cal_id]

            raw_hrs = (att.check_out - att.check_in).total_seconds() / 3600.0 if (att.check_in and att.check_out) else (att.worked_hours or 0.0)
            break_hrs = emp._get_lunch_break_duration()

            if raw_hrs >= 6.0:
                deducted_break = break_hrs
                net_hrs = max(0.0, raw_hrs - break_hrs)
            elif raw_hrs > 4.0:
                deducted_break = break_hrs / 2.0
                net_hrs = max(0.0, raw_hrs - deducted_break)
            else:
                deducted_break = 0.0
                net_hrs = raw_hrs

            att.attendance_break_hours = deducted_break
            att.net_worked_hours = net_hrs

            # Managers: exempt from hourly lateness and overtime deductions
            if emp.is_manager_exempt():
                att.daily_overtime_hours = 0.0
                att.daily_undertime_hours = 0.0
                att.daily_variance_hours = 0.0
                att.is_public_holiday = False
                continue

            target_date = att.check_in.date()
            is_holiday = target_date in pub_holidays
            att.is_public_holiday = is_holiday

            if is_holiday:
                att.daily_overtime_hours = net_hrs
                att.daily_undertime_hours = 0.0
                att.daily_variance_hours = net_hrs
                continue

            tz_name = emp.tz or (cal.tz if cal else False) or self.env.user.tz or 'Asia/Amman'
            try:
                emp_tz = pytz.timezone(tz_name)
            except Exception:
                emp_tz = pytz.timezone('Asia/Amman')

            check_in_local = att.check_in.astimezone(emp_tz)
            actual_in_hour = check_in_local.hour + (check_in_local.minute / 60.0)
            actual_out_hour = 0.0
            if att.check_out:
                check_out_local = att.check_out.astimezone(emp_tz)
                actual_out_hour = check_out_local.hour + (check_out_local.minute / 60.0)

            dow = str(check_in_local.weekday())
            day_cal = cal.attendance_ids.filtered(lambda a: a.dayofweek == dow) if cal else False
            work_station = getattr(emp, 'employee_work_station', False) or 'factory'
            is_fixed = (work_station == 'headoffice') and bool(day_cal)

            has_planning_slot = False
            planning_slots = False
            if 'planning.slot' in self.env:
                day_start_utc, next_day_start_utc, _ = emp._get_day_utc_bounds(target_date)
                planning_slots = self.env['planning.slot'].sudo().search([
                    ('employee_id', '=', emp.id),
                    ('state', '=', 'published'),
                    ('start_datetime', '<', fields.Datetime.to_string(next_day_start_utc)),
                    ('end_datetime', '>', fields.Datetime.to_string(day_start_utc)),
                ], order='start_datetime asc')
                has_planning_slot = bool(planning_slots)

            min_ot_threshold = 0.75  # 45 minutes
            min_lateness_threshold = 0.25  # 15 minutes

            if is_fixed or has_planning_slot:
                sched_start = None
                sched_end = None
                if has_planning_slot and planning_slots:
                    start_dt = pytz.utc.localize(planning_slots[0].start_datetime).astimezone(emp_tz)
                    end_dt = pytz.utc.localize(planning_slots[-1].end_datetime).astimezone(emp_tz)
                    sched_start = start_dt.hour + (start_dt.minute / 60.0)
                    sched_end = end_dt.hour + (end_dt.minute / 60.0)

                if sched_start is None or sched_end is None:
                    if day_cal:
                        sched_start = min(day_cal.mapped('hour_from'))
                        sched_end = max(day_cal.mapped('hour_to'))
                    else:
                        sched_start = 8.0
                        sched_end = 16.5

                late_delay = max(0.0, actual_in_hour - sched_start)
                early_leave = max(0.0, sched_end - actual_out_hour) if att.check_out else 0.0
                total_fixed_undertime = late_delay + early_leave
                undertime = round(total_fixed_undertime, 2) if total_fixed_undertime >= min_lateness_threshold else 0.0

                if att.check_out:
                    ot_delay = max(0.0, actual_out_hour - sched_end)
                    overtime = round(ot_delay, 2) if ot_delay >= min_ot_threshold else 0.0
                else:
                    overtime = 0.0
            else:
                # Flexible schedule: 8.0h daily target
                standard_target = 8.0
                excess = net_hrs - standard_target
                if excess >= min_ot_threshold:
                    overtime = round(excess, 2)
                    undertime = 0.0
                elif excess < -min_lateness_threshold:
                    overtime = 0.0
                    undertime = round(abs(excess), 2)
                else:
                    overtime = 0.0
                    undertime = 0.0

            att.daily_undertime_hours = undertime
            att.daily_overtime_hours = overtime
            att.daily_variance_hours = round(overtime - undertime, 2)

    def action_approve_factory_overtime(self):
        """Approve daily overtime."""
        for att in self:
            att_ot = att.daily_overtime_hours if att.daily_overtime_hours >= 0.75 else 0.0
            vals = {}
            if hasattr(att, 'overtime_status'):
                vals['overtime_status'] = 'approved' if att_ot >= 0.75 else 'refused'
            if hasattr(att, 'validated_overtime_hours'):
                vals['validated_overtime_hours'] = att_ot
            if vals:
                att.sudo().write(vals)

            if hasattr(att, 'linked_overtime_ids') and att.linked_overtime_ids:
                att.linked_overtime_ids.sudo().write({
                    'status': 'approved' if att_ot >= 0.75 else 'refused',
                    'duration': att_ot,
                })
        return True

    def action_refuse_factory_overtime(self):
        """Refuse daily overtime."""
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
        return True

    def action_approve_overtime(self):
        """Standard Odoo action_approve_overtime override."""
        self.action_approve_factory_overtime()
        if hasattr(super(), 'action_approve_overtime'):
            try:
                super().action_approve_overtime()
            except Exception:
                pass
        return True
