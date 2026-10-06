# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models

from . import pfr_utils as U


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    attendance_break_hours = fields.Float(
        string="Lunch Break Deducted", compute="_compute_pfr_metrics", store=False)
    net_worked_hours = fields.Float(
        string="Net Worked Hours", compute="_compute_pfr_metrics", store=False)
    daily_undertime_hours = fields.Float(
        string="Daily Lateness (Deduction)", compute="_compute_pfr_metrics", store=False,
        help="Hours short of the shift (after the 15 min grace).")
    daily_overtime_hours = fields.Float(
        string="Daily Extra Hours", compute="_compute_pfr_metrics", store=False,
        help="Hours beyond the shift (eligible after 45 min).")
    daily_variance_hours = fields.Float(
        string="Daily Variance (Net)", compute="_compute_pfr_metrics", store=False)
    is_public_holiday = fields.Boolean(
        string="Public Holiday", compute="_compute_pfr_metrics", store=False)

    # ------------------------------------------------------------------
    # Daily metrics
    # ------------------------------------------------------------------
    @staticmethod
    def _pfr_raw_hours(att):
        if att.check_in and att.check_out:
            return (att.check_out - att.check_in).total_seconds() / 3600.0
        return att.worked_hours or 0.0

    def _pfr_planning_slots(self, atts):
        """One query for the published planning slots of the given attendances: {emp_id: slots}."""
        res = defaultdict(lambda: self.env['planning.slot'] if 'planning.slot' in self.env else False)
        if 'planning.slot' not in self.env or not atts:
            return res
        dates = [a.check_in.date() for a in atts]
        lo, hi = U.utc_bounds(min(dates), max(dates))
        slots = self.env['planning.slot'].sudo().search([
            ('employee_id', 'in', atts.employee_id.ids), ('state', '=', 'published'),
            ('start_datetime', '<', hi), ('end_datetime', '>', lo)], order='start_datetime asc')
        for s in slots:
            res[s.employee_id.id] = res[s.employee_id.id] | s
        return res

    def _pfr_fixed_bounds(self, emp, tz, local_day, emp_slots):
        """(start_hour, end_hour) of the fixed shift on this local day, or None when unscheduled."""
        if emp_slots:
            slots = emp_slots.filtered(
                lambda s: s.start_datetime and s.end_datetime
                and U.local_date(s.start_datetime, tz) <= local_day <= U.local_date(s.end_datetime, tz))
            if slots:
                return U.local_hour(slots[0].start_datetime, tz), U.local_hour(slots[-1].end_datetime, tz)
        cal = emp.resource_calendar_id or emp.company_id.resource_calendar_id
        lines = cal.attendance_ids.filtered(lambda a: a.dayofweek == str(local_day.weekday())) if cal else False
        if lines:
            return min(lines.mapped('hour_from')), max(lines.mapped('hour_to'))
        return None

    @api.depends('check_in', 'check_out', 'worked_hours', 'employee_id')
    def _compute_pfr_metrics(self):
        zero = dict.fromkeys(('attendance_break_hours', 'net_worked_hours', 'daily_undertime_hours',
                              'daily_overtime_hours', 'daily_variance_hours'), 0.0)
        zero['is_public_holiday'] = False
        ready = getattr(self.env.registry, 'ready', True)
        if not ready or self.env.context.get('install_mode') or self.env.context.get('module_installation'):
            for att in self:
                att.update(zero)
            return
        valid = self.filtered(lambda a: a.check_in and a.employee_id and a.worked_hours)
        for att in self - valid:
            att.update(zero)
        if not valid:
            return

        ledger = self.env['pfr.day.ledger']
        dates = [a.check_in.date() for a in valid]
        holidays = ledger.public_holiday_dates(min(dates) - timedelta(days=1), max(dates) + timedelta(days=1))
        slots_by_emp = self._pfr_planning_slots(valid)
        emp_info = {}

        for att in valid:
            emp = att.employee_id
            if emp.id not in emp_info:
                emp_info[emp.id] = (emp._get_lunch_break_duration(), emp.is_manager_exempt(),
                                    emp._pfr_tz(), emp._pfr_is_fixed_schedule())
            break_hrs, is_manager, tz, fixed = emp_info[emp.id]
            net, deducted = U.net_hours(self._pfr_raw_hours(att), break_hrs)
            vals = dict(zero, attendance_break_hours=deducted, net_worked_hours=net)
            local_day = U.local_date(att.check_in, tz)

            if not is_manager:
                if local_day in ledger.holidays_for(holidays, emp.resource_calendar_id):
                    vals.update(is_public_holiday=True, daily_overtime_hours=net, daily_variance_hours=net)
                else:
                    ot, ut = self._pfr_day_ot_ut(att, emp, tz, fixed, local_day, net, slots_by_emp[emp.id])
                    vals.update(daily_overtime_hours=ot, daily_undertime_hours=ut,
                                daily_variance_hours=round(ot - ut, 2))
            att.update(vals)

    def _pfr_day_ot_ut(self, att, emp, tz, fixed, local_day, net, emp_slots):
        bounds = self._pfr_fixed_bounds(emp, tz, local_day, emp_slots) if fixed else None
        if bounds is None:
            # Flexible rule: net hours against the 8h daily target.
            excess = net - U.DAILY_HOURS
            if excess >= U.OT_MIN_HOURS:
                return round(excess, 2), 0.0
            if excess < -U.LATE_MIN_HOURS:
                return 0.0, round(-excess, 2)
            return 0.0, 0.0
        # Fixed rule: check-in delay + early departure = undertime; late check-out = overtime.
        sched_start, sched_end = bounds
        late = max(0.0, U.local_hour(att.check_in, tz) - sched_start)
        early = ot_delay = 0.0
        if att.check_out:
            actual_out = U.local_hour(att.check_out, tz)
            early = max(0.0, sched_end - actual_out)
            ot_delay = max(0.0, actual_out - sched_end)
        ut = round(late + early, 2) if late + early >= U.LATE_MIN_HOURS else 0.0
        ot = round(ot_delay, 2) if ot_delay >= U.OT_MIN_HOURS else 0.0
        return ot, ut

    # ------------------------------------------------------------------
    # Core overtime fields follow the daily metrics
    # ------------------------------------------------------------------
    @api.depends('daily_overtime_hours', 'employee_id')
    def _compute_overtime_hours(self):
        for att in self:
            exempt = att.employee_id and att.employee_id.is_manager_exempt()
            att.overtime_hours = 0.0 if exempt else (att.daily_overtime_hours or 0.0)

    @api.depends('daily_overtime_hours')
    def _compute_eligible_overtime(self):
        for att in self:
            att.eligible_overtime = att.daily_overtime_hours >= U.OT_MIN_HOURS

    # ------------------------------------------------------------------
    # Approval
    # ------------------------------------------------------------------
    def write(self, vals):
        status = vals.get('overtime_status')
        if status in ('approved', 'refused') and 'validated_overtime_hours' not in vals and len(self) > 1:
            # validated hours are per record: write one by one
            res = True
            for att in self:
                res = att.write(vals) and res
            return res
        if status == 'refused' and 'validated_overtime_hours' not in vals:
            vals = dict(vals, validated_overtime_hours=0.0)
        elif status == 'approved' and 'validated_overtime_hours' not in vals:
            ot = self.daily_overtime_hours
            vals = dict(vals, validated_overtime_hours=ot if ot >= U.OT_MIN_HOURS else 0.0)
        return super().write(vals)

    def _pfr_sync_overtime_lines(self, att, status, hours):
        if 'hr.attendance.overtime.line' not in self.env or not att.check_in or not att.employee_id:
            return
        Line = self.env['hr.attendance.overtime.line'].sudo()
        if 'linked_overtime_ids' in att._fields and att.linked_overtime_ids:
            lines = att.linked_overtime_ids.sudo()
        else:
            lines = Line.search([('employee_id', '=', att.employee_id.id), ('date', '=', att.check_in.date())])
        vals = {'status': status, 'duration': hours}
        if status == 'approved':
            vals['manual_duration'] = hours
        if lines:
            lines.write(vals)
        elif status == 'approved':
            Line.create(dict(vals, employee_id=att.employee_id.id, date=att.check_in.date(),
                             compensable_as_leave=True))

    def action_approve_factory_overtime(self):
        for att in self:
            ot = att.daily_overtime_hours if att.daily_overtime_hours >= U.OT_MIN_HOURS else 0.0
            status = 'approved' if ot else 'refused'
            att.sudo().write({'overtime_status': status, 'validated_overtime_hours': ot})
            self._pfr_sync_overtime_lines(att, status, ot)
        return True

    def action_refuse_factory_overtime(self):
        for att in self:
            att.sudo().write({'overtime_status': 'refused', 'validated_overtime_hours': 0.0})
            self._pfr_sync_overtime_lines(att, 'refused', 0.0)
        return True

    def action_approve_overtime(self):
        try:
            res = super().action_approve_overtime()
        except Exception:
            res = self.action_approve_factory_overtime()
        for att in self:
            ot = att.daily_overtime_hours if att.daily_overtime_hours >= U.OT_MIN_HOURS else 0.0
            att.sudo().write({'validated_overtime_hours': ot,
                              'overtime_status': 'approved' if ot else 'refused'})
        return res

    def _check_weekly_overtime_eligibility(self):
        others = self.filtered(lambda a: a.daily_overtime_hours < U.OT_MIN_HOURS)
        if others and hasattr(super(), '_check_weekly_overtime_eligibility'):
            super(HrAttendance, others)._check_weekly_overtime_eligibility()
