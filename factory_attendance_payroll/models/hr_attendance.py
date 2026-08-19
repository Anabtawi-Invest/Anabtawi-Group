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
                # Up to 15 mins lateness/shortfall is forgiven (0.0 variance)
                attendance.daily_variance_hours = 0.0

    @api.depends('worked_hours', 'employee_id')
    def _compute_overtime_hours(self):
        valid_attendances = self.filtered(lambda a: a.employee_id and a.check_in)
        if not valid_attendances:
            for attendance in self:
                attendance.overtime_hours = 0.0
            return

        validated_set = []
        if 'hr.work.entry' in self.env:
            WorkEntry = self.env['hr.work.entry'].sudo()
            we_fields = WorkEntry._fields
            start_field = 'date_start' if 'date_start' in we_fields else ('date_from' if 'date_from' in we_fields else None)
            stop_field = 'date_stop' if 'date_stop' in we_fields else ('date_to' if 'date_to' in we_fields else None)
            if start_field and stop_field:
                emp_ids = valid_attendances.mapped('employee_id').ids
                min_check_in = min(valid_attendances.mapped('check_in'))
                max_check_in = max(valid_attendances.mapped('check_in'))
                work_entries = WorkEntry.search([
                    ('employee_id', 'in', emp_ids),
                    (start_field, '<=', max_check_in),
                    (stop_field, '>=', min_check_in),
                    ('state', '=', 'validated')
                ])
                for we in work_entries:
                    st = getattr(we, start_field, None)
                    sp = getattr(we, stop_field, None)
                    if st and sp:
                        validated_set.append((we.employee_id.id, st, sp))

        for attendance in self:
            try:
                is_validated = False
                if attendance.employee_id and attendance.check_in and validated_set:
                    for emp_id, st, sp in validated_set:
                        if emp_id == attendance.employee_id.id and st <= attendance.check_in <= sp:
                            is_validated = True
                            break

                if is_validated:
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

    def _update_overtime(self, attendance_domain=None):
        """
        Overrides native Odoo overtime generator to force native extra hours tables
        (hr.attendance.overtime / hr.attendance.overtime.line) to evaluate Net Worked Hours
        after lunch break deduction. Batched for high efficiency.
        """
        res = super()._update_overtime(attendance_domain=attendance_domain)
        valid_atts = self.filtered(lambda a: a.employee_id and a.worked_hours and a.check_in)
        if not valid_atts:
            return res

        emp_ids = valid_atts.mapped('employee_id').ids
        dates = list(set(att.check_in.date() for att in valid_atts))

        ot_recs_by_emp_date = {}
        if 'hr.attendance.overtime' in self.env:
            ot_recs = self.env['hr.attendance.overtime'].sudo().search([
                ('employee_id', 'in', emp_ids),
                ('date', 'in', dates)
            ])
            for rec in ot_recs:
                ot_recs_by_emp_date[(rec.employee_id.id, rec.date)] = rec

        ot_lines_by_emp_date = {}
        if 'hr.attendance.overtime.line' in self.env:
            ot_lines = self.env['hr.attendance.overtime.line'].sudo().search([
                ('employee_id', 'in', emp_ids),
                ('date', 'in', dates)
            ])
            for line in ot_lines:
                ot_lines_by_emp_date[(line.employee_id.id, line.date)] = line

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

                standard_target = 8.0
                excess = net_hrs - standard_target
                min_ot_threshold = 0.75  # 45 minutes
                att_date = att.check_in.date()
                key = (att.employee_id.id, att_date)

                if excess < min_ot_threshold:
                    if key in ot_recs_by_emp_date:
                        ot_recs_by_emp_date[key].sudo().write({'duration': 0.0})
                    if key in ot_lines_by_emp_date:
                        ot_lines_by_emp_date[key].sudo().write({'duration': 0.0, 'manual_duration': 0.0})
                else:
                    if key in ot_recs_by_emp_date:
                        ot_recs_by_emp_date[key].sudo().write({'duration': excess})
            except Exception:
                pass
        return res
