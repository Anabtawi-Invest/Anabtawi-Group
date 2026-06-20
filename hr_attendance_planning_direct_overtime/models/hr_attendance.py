from odoo import models


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    def _update_overtime(self, attendance_domain=None):
        result = super()._update_overtime(attendance_domain=attendance_domain)
        impacted_attendances = (
            self | self.env["hr.attendance"].search(attendance_domain or [])
        ).filtered(lambda att: att.check_in and att.check_out and att.employee_id)
        self._apply_planning_direct_overtime(impacted_attendances)
        return result

    def _apply_planning_direct_overtime(self, attendances):
        if not attendances or "planning.slot" not in self.env:
            return

        overtime_line_model = self.env["hr.attendance.overtime.line"]
        planning_slot_model = self.env["planning.slot"].sudo()

        for attendance in attendances:
            employee = attendance.employee_id
            if not employee.resource_id:
                continue

            version = (
                employee.sudo()._get_version(attendance.check_in.date())
                if hasattr(employee, "_get_version")
                else employee.version_id
            )
            if not version:
                continue
            if (version.work_entry_source or "").strip() != "planning":
                continue
            if not version.overtime_from_attendance:
                continue

            slots = planning_slot_model.search(
                [
                    ("resource_id", "=", employee.resource_id.id),
                    ("state", "=", "published"),
                    ("start_datetime", "<", attendance.check_out),
                    ("end_datetime", ">", attendance.check_in),
                ],
                order="start_datetime asc, id asc",
            )
            if not slots:
                continue

            plan_start = min(slots.mapped("start_datetime"))
            plan_end = max(slots.mapped("end_datetime"))

            early_extra = 0.0
            if attendance.check_in < plan_start:
                early_extra = (plan_start - attendance.check_in).total_seconds() / 3600.0

            late_extra = 0.0
            if attendance.check_out > plan_end:
                late_extra = (attendance.check_out - plan_end).total_seconds() / 3600.0

            direct_overtime = round(max(0.0, early_extra + late_extra), 3)

            overtime_lines = overtime_line_model.search(
                [
                    ("employee_id", "=", employee.id),
                    ("time_start", "=", attendance.check_in),
                    ("time_stop", "=", attendance.check_out),
                ],
                order="id asc",
            )

            if direct_overtime <= 0.0:
                overtime_lines.unlink()
                continue

            if overtime_lines:
                primary_line = overtime_lines[:1]
                extra_lines = overtime_lines[1:]
                primary_line.write(
                    {
                        "duration": direct_overtime,
                        "manual_duration": direct_overtime,
                    }
                )
                extra_lines.unlink()
                continue

            vals = {
                "employee_id": employee.id,
                "date": attendance.date,
                "time_start": attendance.check_in,
                "time_stop": attendance.check_out,
                "duration": direct_overtime,
                "manual_duration": direct_overtime,
                "amount_rate": 1.0,
            }
            default_rule = version.ruleset_id.rule_ids.sorted("sequence")[:1]
            if default_rule:
                vals["rule_ids"] = [(6, 0, default_rule.ids)]
                vals.update(default_rule._extra_overtime_vals())
            overtime_line_model.create(vals)

