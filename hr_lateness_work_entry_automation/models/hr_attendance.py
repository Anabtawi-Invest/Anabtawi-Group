from odoo import api, models


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        recompute_map = self.env["hr.employee"]._lat_prepare_recompute_map()
        for attendance in records.filtered("employee_id"):
            self.env["hr.employee"]._lat_collect_recompute_map_entry(
                recompute_map,
                attendance.employee_id,
                attendance.check_in,
                attendance.check_out or attendance.check_in,
            )
        self.env["hr.employee"]._lat_recompute_from_map(recompute_map)
        return records

    def write(self, vals):
        recompute_map = self.env["hr.employee"]._lat_prepare_recompute_map()
        for attendance in self.filtered("employee_id"):
            self.env["hr.employee"]._lat_collect_recompute_map_entry(
                recompute_map,
                attendance.employee_id,
                attendance.check_in,
                attendance.check_out or attendance.check_in,
            )

        result = super().write(vals)

        for attendance in self.filtered("employee_id"):
            self.env["hr.employee"]._lat_collect_recompute_map_entry(
                recompute_map,
                attendance.employee_id,
                attendance.check_in,
                attendance.check_out or attendance.check_in,
            )

        self.env["hr.employee"]._lat_recompute_from_map(recompute_map)
        return result

    def unlink(self):
        recompute_map = self.env["hr.employee"]._lat_prepare_recompute_map()
        for attendance in self.filtered("employee_id"):
            self.env["hr.employee"]._lat_collect_recompute_map_entry(
                recompute_map,
                attendance.employee_id,
                attendance.check_in,
                attendance.check_out or attendance.check_in,
            )
        result = super().unlink()
        self.env["hr.employee"]._lat_recompute_from_map(recompute_map)
        return result
