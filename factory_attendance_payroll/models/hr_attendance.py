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
        help="Daily variance against target: negative for lateness/shortfalls, positive for overtime."
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
            min_ot_threshold = 0.75  # 45 minutes

            if excess >= min_ot_threshold:
                attendance.daily_variance_hours = excess
            elif excess < 0.0:
                attendance.daily_variance_hours = excess
            else:
                attendance.daily_variance_hours = 0.0

    @api.depends('worked_hours', 'employee_id')
    def _compute_overtime_hours(self):
        for attendance in self:
            try:
                # Check if linked work entry is validated
                is_validated = False
                if 'hr.work.entry' in self.env and attendance.check_in and attendance.employee_id:
                    WorkEntry = self.env['hr.work.entry'].sudo()
                    we_fields = WorkEntry._fields
                    start_field = 'date_start' if 'date_start' in we_fields else ('date_from' if 'date_from' in we_fields else None)
                    stop_field = 'date_stop' if 'date_stop' in we_fields else ('date_to' if 'date_to' in we_fields else None)
                    if start_field and stop_field:
                        we = WorkEntry.search([
                            ('employee_id', '=', attendance.employee_id.id),
                            (start_field, '<=', attendance.check_in),
                            (stop_field, '>=', attendance.check_in),
                            ('state', '=', 'validated')
                        ], limit=1)
                        if we:
                            is_validated = True

                if is_validated:
                    # Do not modify native overtime_hours if linked work entry is validated
                    continue

                raw_hrs = attendance.worked_hours or 0.0
                break_hrs = attendance.employee_id._get_lunch_break_duration() if attendance.employee_id else 1.0
                net_hrs = max(0.0, raw_hrs - break_hrs) if raw_hrs >= 6.0 else raw_hrs
                excess = net_hrs - 8.0
                if excess >= 0.75:
                    attendance.overtime_hours = excess
                else:
                    attendance.overtime_hours = 0.0
            except Exception:
                pass
