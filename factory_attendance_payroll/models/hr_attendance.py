# -*- coding: utf-8 -*-
from odoo import models, fields, api

class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    attendance_break_hours = fields.Float(
        string="Lunch Break Deducted",
        compute="_compute_factory_attendance_metrics",
        store=True,
        help="Break hours deducted (1.0h for Factory/Branch, 0.5h for Head Office)."
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

    @api.depends('worked_hours', 'employee_id')
    def _compute_factory_attendance_metrics(self):
        for attendance in self:
            if not attendance.employee_id or not attendance.worked_hours:
                attendance.attendance_break_hours = 0.0
                attendance.net_worked_hours = 0.0
                attendance.daily_undertime_hours = 0.0
                attendance.daily_overtime_hours = 0.0
                attendance.daily_variance_hours = 0.0
                continue

            raw_hrs = attendance.worked_hours
            break_hrs = attendance.employee_id._get_lunch_break_duration()

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

            target_date = attendance.check_in.date() if attendance.check_in else False
            is_pub_holiday = attendance.employee_id._is_public_holiday(target_date) if (attendance.employee_id and target_date) else False
            expected_hrs = attendance.employee_id._get_expected_hours_on_day(target_date) if (attendance.employee_id and target_date) else 8.0
            is_non_working_day = is_pub_holiday or (expected_hrs <= 0.0)

            if is_non_working_day:
                # Public Holiday or Non-working Day: All net worked hours are extra hours!
                attendance.daily_overtime_hours = net_hrs
                attendance.daily_undertime_hours = 0.0
                attendance.daily_variance_hours = net_hrs
            else:
                standard_target = expected_hrs if expected_hrs > 0 else 8.0
                excess = net_hrs - standard_target
                min_ot_threshold = 0.75         # 45 minutes Overtime threshold
                min_lateness_threshold = 0.25   # 15 minutes Lateness Grace Period

                if excess >= min_ot_threshold:
                    attendance.daily_overtime_hours = excess
                    attendance.daily_undertime_hours = 0.0
                    attendance.daily_variance_hours = excess
                elif excess < -min_lateness_threshold:
                    attendance.daily_overtime_hours = 0.0
                    attendance.daily_undertime_hours = abs(excess)
                    attendance.daily_variance_hours = excess
                else:
                    attendance.daily_overtime_hours = 0.0
                    attendance.daily_undertime_hours = 0.0
                    attendance.daily_variance_hours = 0.0

    @api.depends('worked_hours', 'employee_id')
    def _compute_overtime_hours(self):
        """High-performance in-memory calculation (0 DB queries per row)."""
        for attendance in self:
            if not attendance.employee_id or not attendance.worked_hours:
                attendance.overtime_hours = 0.0
                continue

            raw_hrs = attendance.worked_hours or 0.0
            break_hrs = attendance.employee_id._get_lunch_break_duration()
            net_hrs = max(0.0, raw_hrs - break_hrs) if raw_hrs >= 6.0 else raw_hrs
            target_date = attendance.check_in.date() if attendance.check_in else False
            is_pub_holiday = attendance.employee_id._is_public_holiday(target_date) if (attendance.employee_id and target_date) else False
            expected_hrs = attendance.employee_id._get_expected_hours_on_day(target_date) if (attendance.employee_id and target_date) else 8.0
            if is_pub_holiday or expected_hrs <= 0.0:
                attendance.overtime_hours = net_hrs
            else:
                standard_target = expected_hrs if expected_hrs > 0 else 8.0
                excess = net_hrs - standard_target
                attendance.overtime_hours = excess if excess >= 0.75 else 0.0

    def action_approve_factory_overtime(self):
        """
        Explicit HR Action to validate and approve daily overtime for factory attendance.
        Sets overtime_status to 'approved' and updates validated_overtime_hours from daily_overtime_hours.
        """
        for att in self:
            att_ot = att.daily_overtime_hours if att.daily_overtime_hours > 0 else 0.0
            if att_ot <= 0:
                # If there are no daily extra hours, clear validated overtime
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

            # Ensure public holiday attendance work entries are synced
            if att.check_in and att.employee_id and att.employee_id._is_public_holiday(att.check_in.date()):
                att.employee_id._sync_public_holiday_work_entries(att.check_in.date(), att.check_in.date())
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
                att.validated_overtime_hours = att.daily_overtime_hours if att.daily_overtime_hours > 0 else 0.0
            elif att.overtime_status == 'refused':
                att.validated_overtime_hours = 0.0

    def write(self, vals):
        if vals.get('overtime_status') == 'approved' and 'validated_overtime_hours' not in vals:
            for att in self:
                att_ot = att.daily_overtime_hours if att.daily_overtime_hours > 0 else 0.0
                vals['validated_overtime_hours'] = att_ot
        elif vals.get('overtime_status') == 'refused' and 'validated_overtime_hours' not in vals:
            vals['validated_overtime_hours'] = 0.0
        res = super().write(vals)
        for att in self:
            if att.check_in and att.employee_id and att.employee_id._is_public_holiday(att.check_in.date()):
                att.employee_id._sync_public_holiday_work_entries(att.check_in.date(), att.check_in.date())
        return res

    @api.depends('worked_hours', 'employee_id', 'daily_overtime_hours')
    def _compute_eligible_overtime(self):
        """
        Factory Attendance Override:
        Attendance records with positive Daily Extra Hours are eligible for approval.
        """
        if hasattr(super(), '_compute_eligible_overtime'):
            try:
                super()._compute_eligible_overtime()
            except Exception:
                pass
        for attendance in self:
            if attendance.daily_overtime_hours > 0:
                attendance.eligible_overtime = True
            else:
                attendance.eligible_overtime = False

    def _check_weekly_overtime_eligibility(self):
        """
        Factory Attendance Override:
        Allow approval if attendance has valid positive extra hours.
        """
        factory_atts = self.filtered(lambda a: a.daily_overtime_hours > 0)
        other_atts = self - factory_atts
        if other_atts and hasattr(super(), '_check_weekly_overtime_eligibility'):
            try:
                super(HrAttendance, other_atts)._check_weekly_overtime_eligibility()
            except Exception:
                pass

    def action_approve_overtime(self):
        """
        Standard Odoo action_approve_overtime override:
        Approves extra hours using daily_overtime_hours.
        """
        for att in self:
            att_ot = att.daily_overtime_hours if att.daily_overtime_hours > 0 else 0.0
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
            att_ot = att.daily_overtime_hours if att.daily_overtime_hours > 0 else 0.0
            if hasattr(att, 'validated_overtime_hours'):
                att.sudo().write({
                    'validated_overtime_hours': att_ot,
                    'overtime_status': 'approved' if att_ot > 0 else 'refused'
                })
        return res

    def _update_overtime(self, attendance_domain=None):
        """
        Batch-optimized overtime generator: Pre-fetches all overtime lines
        in 1 bulk query and ensures overtime lines match daily_overtime_hours.
        """
        res = super()._update_overtime(attendance_domain=attendance_domain)
        valid_atts = self.filtered(lambda a: a.employee_id and a.worked_hours and a.check_in)
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
                is_pub_holiday = att.employee_id._is_public_holiday(target_date) if (att.employee_id and target_date) else False
                expected_hrs = att.employee_id._get_expected_hours_on_day(target_date) if (att.employee_id and target_date) else 8.0
                if is_pub_holiday or expected_hrs <= 0.0:
                    excess = net_hrs
                    min_ot_threshold = 0.01
                else:
                    standard_target = expected_hrs if expected_hrs > 0 else 8.0
                    excess = net_hrs - standard_target
                    min_ot_threshold = 0.75

                att_date = att.check_in.date()
                key = (att.employee_id.id, att_date)

                ot_rec = ot_by_key.get(key)
                ot_line = ot_lines_by_key.get(key)

                if excess < min_ot_threshold:
                    if ot_rec:
                        ot_rec.sudo().write({'duration': 0.0})
                    if ot_line:
                        ot_line.sudo().write({'duration': 0.0, 'manual_duration': 0.0})
                else:
                    if ot_rec:
                        ot_rec.sudo().write({'duration': excess})
            except Exception:
                pass
        return res
