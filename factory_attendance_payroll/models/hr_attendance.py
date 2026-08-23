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

    daily_variance_hours = fields.Float(
        string="Daily Variance (Lateness/OT)",
        compute="_compute_factory_attendance_metrics",
        store=True,
        help="Daily variance against target: negative for lateness/shortfalls, positive for overtime. Up to 15 mins lateness is forgiven."
    )

    @api.depends('worked_hours', 'employee_id')
    def _compute_factory_attendance_metrics(self):
        for attendance in self:
            if not attendance.employee_id or not attendance.worked_hours:
                attendance.attendance_break_hours = 0.0
                attendance.net_worked_hours = 0.0
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

            standard_target = 8.0
            excess = net_hrs - standard_target
            min_ot_threshold = 0.75         # 45 minutes Overtime threshold
            min_lateness_threshold = 0.25   # 15 minutes Lateness Grace Period

            if excess >= min_ot_threshold:
                attendance.daily_variance_hours = excess
            elif excess < -min_lateness_threshold:
                attendance.daily_variance_hours = excess
            else:
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
            excess = net_hrs - 8.0
            attendance.overtime_hours = excess if excess >= 0.75 else 0.0

    def action_approve_factory_overtime(self):
        """
        Explicit HR Action to validate and approve daily overtime for factory attendance.
        Sets overtime_status to 'approved' and updates validated_overtime_hours.
        """
        for att in self:
            att_ot = att.daily_variance_hours if att.daily_variance_hours >= 0.75 else (att.overtime_hours or 0.0)
            if att_ot < 0.75:
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
                att.linked_overtime_ids.sudo().write({'status': 'refused'})
            elif 'hr.attendance.overtime.line' in self.env:
                att_date = att.check_in.date() if att.check_in else None
                if att_date and att.employee_id:
                    ot_lines = self.env['hr.attendance.overtime.line'].sudo().search([
                        ('employee_id', '=', att.employee_id.id),
                        ('date', '=', att_date)
                    ])
                    if ot_lines:
                        ot_lines.write({'status': 'refused'})
        return True

    @api.onchange('overtime_status')
    def _onchange_overtime_status(self):
        for att in self:
            if att.overtime_status == 'approved':
                att.validated_overtime_hours = att.daily_variance_hours if att.daily_variance_hours >= 0.75 else (att.overtime_hours or 0.0)
            elif att.overtime_status == 'refused':
                att.validated_overtime_hours = 0.0

    def write(self, vals):
        if vals.get('overtime_status') == 'approved' and 'validated_overtime_hours' not in vals:
            for att in self:
                att_ot = att.daily_variance_hours if att.daily_variance_hours >= 0.75 else (att.overtime_hours or 0.0)
                if att_ot >= 0.75:
                    vals['validated_overtime_hours'] = att_ot
        elif vals.get('overtime_status') == 'refused' and 'validated_overtime_hours' not in vals:
            vals['validated_overtime_hours'] = 0.0
        return super().write(vals)

    def _update_overtime(self, attendance_domain=None):
        """
        Batch-optimized overtime generator: Pre-fetches all overtime lines
        in 1 bulk query instead of N individual database searches.
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

                excess = net_hrs - 8.0
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
