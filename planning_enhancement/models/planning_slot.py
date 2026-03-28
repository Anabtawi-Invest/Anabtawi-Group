import logging
import traceback

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PlanningSlot(models.Model):
    _inherit = "planning.slot"

    extra_hours_display = fields.Float(
        string="Extra Hours",
        compute="_compute_extra_hours_display",
        readonly=True,
    )
    convert_ot_to_leave = fields.Boolean(
        string="Convert Extra Hours to Time Off",
        copy=False,
    )
    ot_leave_id = fields.Many2one(
        "hr.leave.type",
        string="Time Off Type",
        copy=False,
    )
    ot_generated_leave_id = fields.Many2one(
        "hr.leave.allocation",
        string="Generated Time Off Allocation",
        readonly=True,
        copy=False,
    )

    @api.depends("resource_id", "resource_id.employee_id", "resource_id.employee_id.total_overtime")
    def _compute_extra_hours_display(self):
        for slot in self:
            slot.extra_hours_display = slot.resource_id.employee_id.total_overtime or 0.0

    def _get_overtime_deductible_leave_type(self, employee):
        self.ensure_one()
        if self.ot_leave_id:
            return self.ot_leave_id
        raise ValidationError(_("Please select a Time Off Type before publishing the shift."))

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

    def action_send(self):
        _logger.info("[planning_enhancement][ot_convert] action_send_start slot_ids=%s", self.ids)
        result = super().action_send()
        self._handle_ot_conversion()
        _logger.info("[planning_enhancement][ot_convert] action_send_done slot_ids=%s", self.ids)
        return result

    def _handle_ot_conversion(self):
        Allocation = self.env["hr.leave.allocation"]
        Leave = self.env["hr.leave"]
        for slot in self:
            if not slot.convert_ot_to_leave:
                continue
            if slot.ot_generated_leave_id:
                raise ValidationError(_("Time Off already created for this shift."))

            hours = slot.allocated_hours or 0.0
            if hours <= 0:
                raise ValidationError(_("Allocated hours must be greater than 0."))

            employee = slot.resource_id.employee_id
            if not employee:
                raise ValidationError(_("No employee linked to this shift."))

            leave_type = slot._get_overtime_deductible_leave_type(employee)
            if not leave_type:
                raise ValidationError(_("Please select a Time Off Type before publishing the shift."))

            allocation_date = fields.Date.to_date(slot.start_datetime)
            hours_per_day = employee._get_hours_per_day(allocation_date) or 8.0
            deductible = Leave._get_deductible_employee_overtime(employee)[employee]
            if hours > deductible + 1e-6:
                raise ValidationError(_(
                    "Allocated hours (%.2f) exceed deductible extra hours (%.2f)."
                ) % (hours, deductible))

            allocation_vals = {
                "name": _("Extra Hours Conversion from Published Shift"),
                "employee_id": employee.id,
                "holiday_status_id": leave_type.id,
                "allocation_type": "regular",
                "date_from": allocation_date,
                "date_to": False,
            }
            if leave_type.request_unit == "hour":
                allocation_vals["number_of_hours_display"] = hours
            else:
                allocation_vals["number_of_days_display"] = hours / hours_per_day

            _logger.info(
                (
                    "[planning_enhancement][ot_convert] pre_create slot_id=%s employee_id=%s employee=%s "
                    "total_overtime=%.2f deductible_overtime=%.2f requested_hours=%.2f "
                    "leave_type_id=%s leave_type=%s requires_allocation=%s overtime_deductible=%s vals=%s"
                ),
                slot.id,
                employee.id,
                employee.display_name,
                employee.total_overtime or 0.0,
                deductible or 0.0,
                slot.allocated_hours or 0.0,
                leave_type.id,
                leave_type.display_name,
                leave_type.requires_allocation,
                leave_type.overtime_deductible,
                allocation_vals,
            )
            try:
                allocation = Allocation.sudo().create(allocation_vals)
            except ValidationError as err:
                deductible_after_error = self.env["hr.leave"]._get_deductible_employee_overtime(employee)[employee]
                _logger.warning(
                    (
                        "[planning_enhancement][ot_convert] create_failed slot_id=%s employee_id=%s employee=%s "
                        "error=%s total_overtime=%.2f deductible_overtime=%.2f requested_hours=%.2f "
                        "leave_type_id=%s leave_type=%s requires_allocation=%s overtime_deductible=%s"
                    ),
                    slot.id,
                    employee.id,
                    employee.display_name,
                    str(err),
                    employee.total_overtime or 0.0,
                    deductible_after_error or 0.0,
                    slot.allocated_hours or 0.0,
                    leave_type.id,
                    leave_type.display_name,
                    leave_type.requires_allocation,
                    leave_type.overtime_deductible,
                )
                raise
            try:
                _logger.info(
                    "[planning_enhancement][ot_convert] allocation_created slot_id=%s allocation_id=%s state=%s",
                    slot.id,
                    allocation.id,
                    allocation.state,
                )
                allocation.sudo()._action_validate()
                _logger.info(
                    "[planning_enhancement][ot_convert] allocation_validated slot_id=%s allocation_id=%s state=%s",
                    slot.id,
                    allocation.id,
                    allocation.state,
                )
            except Exception as err:
                _logger.error(
                    (
                        "[planning_enhancement][ot_convert] allocation_validate_failed slot_id=%s allocation_id=%s "
                        "error=%s traceback=%s"
                    ),
                    slot.id,
                    allocation.id if allocation else None,
                    str(err),
                    traceback.format_exc(),
                )
                raise

            try:
                slot.write({
                    "name": _("Time Off"),
                    "color": 1,
                    "convert_ot_to_leave": False,
                    "ot_generated_leave_id": allocation.id,
                })
                _logger.info(
                    "[planning_enhancement][ot_convert] slot_linked slot_id=%s allocation_id=%s",
                    slot.id,
                    allocation.id,
                )
            except Exception as err:
                _logger.error(
                    (
                        "[planning_enhancement][ot_convert] slot_link_failed slot_id=%s allocation_id=%s "
                        "error=%s traceback=%s"
                    ),
                    slot.id,
                    allocation.id,
                    str(err),
                    traceback.format_exc(),
                )
                raise

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
