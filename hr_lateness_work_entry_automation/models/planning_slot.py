import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class PlanningSlot(models.Model):
    _inherit = "planning.slot"

    def _lat_get_slot_employee(self):
        self.ensure_one()
        if not self.resource_id:
            return self.env["hr.employee"]
        return self.resource_id.with_context(active_test=False).employee_id

    def _lat_collect_recompute_map_for_slot(self, recompute_map):
        self.ensure_one()
        employee = self._lat_get_slot_employee()
        self.env["hr.employee"]._lat_collect_recompute_map_entry(
            recompute_map,
            employee,
            self.start_datetime,
            self.end_datetime,
        )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        recompute_map = self.env["hr.employee"]._lat_prepare_recompute_map()
        for slot in records:
            slot._lat_collect_recompute_map_for_slot(recompute_map)
        _logger.info(
            "[LAT] planning_create trigger slot_ids=%s recompute_map=%s",
            records.ids,
            {employee_id: sorted(days) for employee_id, days in recompute_map.items()},
        )
        self.env["hr.employee"]._lat_recompute_from_map(recompute_map)
        return records

    def write(self, vals):
        recompute_map = self.env["hr.employee"]._lat_prepare_recompute_map()
        for slot in self:
            slot._lat_collect_recompute_map_for_slot(recompute_map)
        _logger.info(
            "[LAT] planning_write_before trigger slot_ids=%s vals_keys=%s recompute_map=%s",
            self.ids,
            sorted(vals.keys()),
            {employee_id: sorted(days) for employee_id, days in recompute_map.items()},
        )

        result = super().write(vals)

        for slot in self:
            slot._lat_collect_recompute_map_for_slot(recompute_map)
        _logger.info(
            "[LAT] planning_write_after trigger slot_ids=%s recompute_map=%s",
            self.ids,
            {employee_id: sorted(days) for employee_id, days in recompute_map.items()},
        )

        self.env["hr.employee"]._lat_recompute_from_map(recompute_map)
        return result

    def unlink(self):
        recompute_map = self.env["hr.employee"]._lat_prepare_recompute_map()
        for slot in self:
            slot._lat_collect_recompute_map_for_slot(recompute_map)
        _logger.info(
            "[LAT] planning_unlink trigger slot_ids=%s recompute_map=%s",
            self.ids,
            {employee_id: sorted(days) for employee_id, days in recompute_map.items()},
        )

        result = super().unlink()
        self.env["hr.employee"]._lat_recompute_from_map(recompute_map)
        return result
