import logging
from odoo import api, models

_logger = logging.getLogger(__name__)


class HrLeave(models.Model):
    _inherit = "hr.leave"

    def _lat_collect_recompute_map_for_leave(self, recompute_map):
        for leave in self.filtered(lambda l: l.employee_id and l.date_from and l.date_to):
            self.env["hr.employee"]._lat_collect_recompute_map_entry(
                recompute_map,
                leave.employee_id,
                leave.date_from,
                leave.date_to,
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        recompute_map = self.env["hr.employee"]._lat_prepare_recompute_map()
        records._lat_collect_recompute_map_for_leave(recompute_map)
        self.env["hr.employee"]._lat_recompute_from_map(recompute_map)
        return records

    def write(self, vals):
        recompute_map = self.env["hr.employee"]._lat_prepare_recompute_map()
        self._lat_collect_recompute_map_for_leave(recompute_map)
        result = super().write(vals)
        self._lat_collect_recompute_map_for_leave(recompute_map)
        self.env["hr.employee"]._lat_recompute_from_map(recompute_map)
        return result

    def unlink(self):
        recompute_map = self.env["hr.employee"]._lat_prepare_recompute_map()
        self._lat_collect_recompute_map_for_leave(recompute_map)
        result = super().unlink()
        self.env["hr.employee"]._lat_recompute_from_map(recompute_map)
        return result
