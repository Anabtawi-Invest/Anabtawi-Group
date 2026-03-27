from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PlanningSlot(models.Model):
    _inherit = "planning.slot"

    extra_hours_display = fields.Float(
        string="Extra Hours",
        compute="_compute_extra_hours_display",
        readonly=True,
    )

    @api.depends("resource_id", "resource_id.employee_id", "resource_id.employee_id.total_overtime")
    def _compute_extra_hours_display(self):
        for slot in self:
            slot.extra_hours_display = slot.resource_id.employee_id.total_overtime or 0.0

    def _check_extra_hours_limit_for_new_shift(self):
        for slot in self:
            max_extra_hours = slot.company_id.planning_max_extra_hours or 0.0
            if max_extra_hours <= 0:
                continue

            employee = slot.resource_id.employee_id
            if not employee:
                continue

            current_extra_hours = employee.total_overtime or 0.0
            if current_extra_hours > max_extra_hours + 1e-6:
                raise UserError(
                    _(
                        "Cannot assign a new shift to %(employee)s because current Extra Hours (%(current).2f) exceed the configured maximum (%(maximum).2f). "
                        "Please convert some hours to Time Off before assigning another shift."
                    )
                    % {
                        "employee": employee.display_name,
                        "current": current_extra_hours,
                        "maximum": max_extra_hours,
                    }
                )

    @api.model_create_multi
    def create(self, vals_list):
        slots = super().create(vals_list)
        slots._check_extra_hours_limit_for_new_shift()
        return slots

    def write(self, vals):
        result = super().write(vals)
        if {"resource_id", "start_datetime", "end_datetime", "allocated_hours"} & set(vals):
            self._check_extra_hours_limit_for_new_shift()
        return result
