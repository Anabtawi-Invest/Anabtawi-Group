import logging
from datetime import timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero

_logger = logging.getLogger(__name__)


class HrLeave(models.Model):
    _inherit = "hr.leave"

    @api.model
    def _fallback_get_requested_hours(self, vals):
        new_leave = self.new(vals)
        new_leave._compute_date_from_to()
        new_leave._compute_duration()
        return max(new_leave.number_of_hours, 0.0)

    @api.model
    def _fallback_get_available_days(self, leave_type, employee, target_date):
        if not leave_type:
            return 0.0
        if not leave_type.requires_allocation:
            return 10 ** 9
        leave_data = leave_type.get_allocation_data(employee, target_date).get(employee, [])
        if not leave_data:
            return 0.0
        return max(leave_data[0][1].get("virtual_remaining_leaves", 0.0), 0.0)

    @api.model
    def _fallback_get_available_hours(self, leave_type, employee, target_date, hours_per_day):
        available = self._fallback_get_available_days(leave_type, employee, target_date)
        if leave_type.request_unit == "hour":
            return available
        return available * hours_per_day

    @api.model
    def _fallback_get_extra_hours(self, employee):
        overtime_map = employee._get_deductible_employee_overtime()
        return max(overtime_map.get(employee, 0.0), 0.0)

    @api.model
    def _fallback_create_extra_allocation(self, employee, extra_type, start_date, hours_to_allocate, hours_per_day):
        if float_is_zero(hours_to_allocate, precision_digits=2):
            return

        allocation_vals = {
            "name": _("Auto Allocation from Extra Hours"),
            "employee_id": employee.id,
            "holiday_status_id": extra_type.id,
            "date_from": start_date,
        }
        if extra_type.request_unit == "hour":
            allocation_vals["number_of_hours_display"] = hours_to_allocate
        else:
            allocation_vals["number_of_days"] = hours_to_allocate / hours_per_day

        allocation = self.env["hr.leave.allocation"].sudo().with_context(
            mail_create_nosubscribe=True
        ).create(allocation_vals)
        allocation._action_validate()

    @api.model
    def _fallback_clean_duration_inputs(self, vals):
        cleaned_vals = dict(vals)
        cleaned_vals.pop("date_from", None)
        cleaned_vals.pop("date_to", None)
        cleaned_vals.pop("number_of_days", None)
        cleaned_vals.pop("number_of_hours", None)
        return cleaned_vals

    @api.model
    def _fallback_datetime_to_request_values(self, utc_dt, employee):
        tz_name = employee.tz or self.env.user.tz or "UTC"
        tz = pytz.timezone(tz_name)
        local_dt = pytz.UTC.localize(utc_dt).astimezone(tz)
        hour_value = local_dt.hour + (local_dt.minute / 60.0) + (local_dt.second / 3600.0)
        return local_dt.date(), hour_value

    @api.model
    def _fallback_split_vals_by_hours(self, vals, employee, first_hours):
        if first_hours <= 0:
            return False

        preview = self.new(vals)
        preview._compute_date_from_to()
        preview._compute_duration()
        total_hours = preview.number_of_hours

        if not preview.date_from or not preview.date_to or first_hours >= total_hours:
            return False

        split_dt = preview.date_from + timedelta(hours=first_hours)
        if split_dt <= preview.date_from or split_dt >= preview.date_to:
            return False

        first_vals = self._fallback_clean_duration_inputs(vals)
        second_vals = self._fallback_clean_duration_inputs(vals)

        start_date, start_hour = self._fallback_datetime_to_request_values(preview.date_from, employee)
        split_date, split_hour = self._fallback_datetime_to_request_values(split_dt, employee)
        end_date, end_hour = self._fallback_datetime_to_request_values(preview.date_to, employee)

        first_vals.update({
            "request_date_from": start_date,
            "request_hour_from": start_hour,
            "request_date_to": split_date,
            "request_hour_to": split_hour,
        })
        second_vals.update({
            "request_date_from": split_date,
            "request_hour_from": split_hour,
            "request_date_to": end_date,
            "request_hour_to": end_hour,
        })
        return first_vals, second_vals

    @api.model
    def _fallback_prepare_leave_vals(self, vals):
        leave_type_id = vals.get("holiday_status_id")
        employee_id = vals.get("employee_id")
        if not leave_type_id or not employee_id:
            return [vals]

        leave_type = self.env["hr.leave.type"].browse(leave_type_id)
        if not leave_type.use_sick_fallback:
            return [vals]

        employee = self.env["hr.employee"].browse(employee_id)
        company = employee.company_id
        extra_type = company.extra_hours_leave_type_id
        annual_type = company.annual_leave_type_id
        unpaid_type = company.unpaid_leave_type_id

        configured_type_ids = {extra_type.id, annual_type.id, unpaid_type.id}
        if leave_type.id in configured_type_ids:
            return [vals]
        if not annual_type:
            raise UserError(_("Please configure Annual Leave Type in Time Off Fallback settings."))

        target_date = fields.Date.to_date(vals.get("request_date_from")) or fields.Date.today()
        hours_per_day = employee._get_hours_per_day(target_date) or 8.0
        requested_hours = self._fallback_get_requested_hours(vals)
        if float_is_zero(requested_hours, precision_digits=2):
            return [vals]

        extra_balance_hours = 0.0
        if extra_type:
            if not extra_type.requires_allocation:
                raise UserError(_("Extra Hours leave type must require allocation."))
            extra_balance_hours = self._fallback_get_extra_hours(employee)
        annual_balance_hours = self._fallback_get_available_hours(annual_type, employee, target_date, hours_per_day)

        _logger.info(
            "Leave fallback start | employee=%s leave_type=%s requested_hours=%.2f extra_hours=%.2f annual_hours=%.2f",
            employee.display_name,
            leave_type.display_name,
            requested_hours,
            extra_balance_hours,
            annual_balance_hours,
        )

        allocations = []
        remaining_hours = requested_hours

        extra_hours = min(remaining_hours, extra_balance_hours)
        if extra_type and not float_is_zero(extra_hours, precision_digits=2):
            allocations.append((extra_type, extra_hours))
            remaining_hours -= extra_hours

        annual_hours = min(remaining_hours, annual_balance_hours)
        if not float_is_zero(annual_hours, precision_digits=2):
            allocations.append((annual_type, annual_hours))
            remaining_hours -= annual_hours

        if remaining_hours > 0:
            if not unpaid_type:
                raise UserError(
                    _("Please configure Unpaid Leave Type in Time Off Fallback settings to cover insufficient balances.")
                )
            allocations.append((unpaid_type, remaining_hours))

        if not allocations:
            return [vals]

        if len(allocations) == 1:
            single_vals = dict(vals)
            single_vals["holiday_status_id"] = allocations[0][0].id
            if allocations[0][0] == extra_type:
                self._fallback_create_extra_allocation(employee, extra_type, target_date, allocations[0][1], hours_per_day)
            _logger.info("Leave fallback result | single leave on %s", allocations[0][0].display_name)
            return [single_vals]

        result_vals = []
        current_vals = dict(vals)
        chunk_count = len(allocations)
        for index, (chunk_type, chunk_hours) in enumerate(allocations):
            if index == chunk_count - 1:
                last_vals = dict(current_vals)
                last_vals["holiday_status_id"] = chunk_type.id
                result_vals.append(last_vals)
                break

            split_result = self._fallback_split_vals_by_hours(current_vals, employee, chunk_hours)
            if not split_result:
                single_vals = dict(vals)
                if annual_balance_hours >= requested_hours:
                    single_vals["holiday_status_id"] = annual_type.id
                else:
                    single_vals["holiday_status_id"] = unpaid_type.id
                _logger.warning(
                    "Leave fallback split failed for chunk=%s hours=%.2f. Fallback to single type_id=%s",
                    chunk_type.display_name,
                    chunk_hours,
                    single_vals["holiday_status_id"],
                )
                return [single_vals]

            first_vals, current_vals = split_result
            first_vals["holiday_status_id"] = chunk_type.id
            result_vals.append(first_vals)

        for leave_vals in result_vals:
            if leave_vals.get("holiday_status_id") == extra_type.id:
                chunk_start = fields.Date.to_date(leave_vals.get("request_date_from")) or target_date
                chunk_hours = self._fallback_get_requested_hours(leave_vals)
                self._fallback_create_extra_allocation(employee, extra_type, chunk_start, chunk_hours, hours_per_day)
                _logger.info(
                    "Leave fallback allocation created for Extra chunk | start=%s hours=%.2f",
                    chunk_start,
                    chunk_hours,
                )

        _logger.info(
            "Leave fallback result | created %s leave chunk(s) with types=%s",
            len(result_vals),
            [vals_item.get("holiday_status_id") for vals_item in result_vals],
        )
        return result_vals

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get("skip_leave_fallback_logic"):
            return super().create(vals_list)

        final_vals_list = []
        for vals in vals_list:
            final_vals_list.extend(self._fallback_prepare_leave_vals(vals))

        return super().create(final_vals_list)
