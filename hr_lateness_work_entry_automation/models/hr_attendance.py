import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


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
        _logger.info(
            "[LAT] attendance_create trigger attendance_ids=%s recompute_map=%s",
            records.ids,
            {employee_id: sorted(days) for employee_id, days in recompute_map.items()},
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
        _logger.info(
            "[LAT] attendance_write_before trigger attendance_ids=%s vals_keys=%s recompute_map=%s",
            self.ids,
            sorted(vals.keys()),
            {employee_id: sorted(days) for employee_id, days in recompute_map.items()},
        )

        result = super().write(vals)

        for attendance in self.filtered("employee_id"):
            self.env["hr.employee"]._lat_collect_recompute_map_entry(
                recompute_map,
                attendance.employee_id,
                attendance.check_in,
                attendance.check_out or attendance.check_in,
            )
        _logger.info(
            "[LAT] attendance_write_after trigger attendance_ids=%s recompute_map=%s",
            self.ids,
            {employee_id: sorted(days) for employee_id, days in recompute_map.items()},
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
        _logger.info(
            "[LAT] attendance_unlink trigger attendance_ids=%s recompute_map=%s",
            self.ids,
            {employee_id: sorted(days) for employee_id, days in recompute_map.items()},
        )
        result = super().unlink()
        self.env["hr.employee"]._lat_recompute_from_map(recompute_map)
        return result
