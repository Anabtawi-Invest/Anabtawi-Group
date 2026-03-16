import logging
import traceback

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.addons.hr_holidays_attendance.models.hr_leave_allocation import HrLeaveAllocation as HrHolidaysAttendanceLeaveAllocation

_logger = logging.getLogger(__name__)


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    employee_overtime = fields.Float(
        compute='_compute_employee_overtime',
        groups='base.group_user',
    )
    is_ot_conversion = fields.Boolean(copy=False)
    ot_conversion_payslip_id = fields.Many2one(
        'hr.payslip',
        copy=False,
        ondelete='set null',
    )
    ot_conversion_input_id = fields.Many2one(
        'hr.payslip.input',
        copy=False,
        ondelete='set null',
    )
    number_of_day_converted = fields.Float(
        string='Converted Days from OT Balance',
        compute='_compute_number_of_day_converted',
        digits=(16, 2),
    )

    @api.depends('employee_id')
    def _compute_employee_overtime(self):
        """Keep popup "Extra Hours Available" aligned with OT wallet source of truth."""
        deductible_by_employee = self.env['hr.leave']._get_deductible_employee_overtime(self.employee_id)
        for alloc in self:
            alloc.employee_overtime = deductible_by_employee[alloc.employee_id] if alloc.employee_id else 0.0

    @api.depends(
        'ot_conversion_payslip_id',
        'ot_conversion_payslip_id.ot_wallet_carry_out_equiv'
    )
    def _compute_number_of_day_converted(self):
        print(545454)
        for alloc in self:
            alloc.number_of_day_converted = 0.0

            if not alloc.is_ot_conversion or not alloc.ot_conversion_payslip_id:
                continue

            payslip = alloc.ot_conversion_payslip_id
            print(payslip)

            # Keep wallet value up to date before exposing converted value.
            payslip.action_rebuild_ot_wallet()

            alloc.number_of_day_converted = (
                    payslip.ot_wallet_carry_out_equiv or 0.0
            )

    def _log_ot_diagnostics(self, employees, vals_list=None, phase='unknown', error_message=None):
        employees = employees.sudo().exists()
        if not employees:
            _logger.warning("[OT DEBUG] phase=%s no_employees error=%s", phase, error_message)
            return

        deductible_by_employee = self.env['hr.leave']._get_deductible_employee_overtime(employees)

        attendance_sums = {}
        for employee, is_compensable, amount in self.env['hr.attendance.overtime.line'].sudo()._read_group(
            domain=[
                ('employee_id', 'in', employees.ids),
                ('status', '=', 'approved'),
            ],
            groupby=['employee_id', 'compensable_as_leave'],
            aggregates=['manual_duration:sum'],
        ):
            attendance_sums.setdefault(employee.id, {'compensable': 0.0, 'non_compensable': 0.0})
            key = 'compensable' if is_compensable else 'non_compensable'
            attendance_sums[employee.id][key] += amount or 0.0

        requested_by_employee = {}
        for vals in vals_list or []:
            employee_id = vals.get('employee_id')
            if not employee_id:
                continue
            requested_by_employee.setdefault(employee_id, 0.0)
            requested_by_employee[employee_id] += (
                vals.get('number_of_hours_display')
                or vals.get('number_of_hours')
                or 0.0
            )

        for employee in employees:
            sums = attendance_sums.get(employee.id, {})
            _logger.warning(
                "[OT DEBUG] phase=%s error=%s employee_id=%s employee=%s widget_total_overtime=%s "
                "deductible=%s approved_compensable=%s approved_non_compensable=%s requested_hours=%s",
                phase,
                error_message,
                employee.id,
                employee.display_name,
                employee.total_overtime,
                deductible_by_employee[employee],
                sums.get('compensable', 0.0),
                sums.get('non_compensable', 0.0),
                requested_by_employee.get(employee.id, 0.0),
            )

    @api.model_create_multi
    def create(self, vals_list):
        def _requested_hours_by_employee(values_list):
            requested = {}
            for values in values_list:
                employee_id = values.get('employee_id')
                if not employee_id:
                    continue
                requested.setdefault(employee_id, 0.0)
                requested[employee_id] += (
                    values.get('number_of_hours_display')
                    or values.get('number_of_hours')
                    or 0.0
                )
            return requested

        try:
            allocations = super().create(vals_list)
        except ValidationError as err:
            employee_ids = [vals.get('employee_id') for vals in vals_list if vals.get('employee_id')]
            employees = self.env['hr.employee'].browse(employee_ids)
            self._log_ot_diagnostics(
                employees=employees,
                vals_list=vals_list,
                phase='allocation_create',
                error_message=str(err),
            )
            _logger.warning(
                "[OT DEBUG TRACE] phase=allocation_create error=%s vals_list=%s\n%s",
                str(err),
                vals_list,
                traceback.format_exc(),
            )
            message = (str(err) or '').lower()
            if 'enough overtime hours' in message:
                requested_by_employee = _requested_hours_by_employee(vals_list)
                deductible_by_employee = self.env['hr.leave']._get_deductible_employee_overtime(employees)
                can_bypass = all(
                    deductible_by_employee[employee] + 1e-6 >= requested_by_employee.get(employee.id, 0.0)
                    for employee in employees
                )
                if can_bypass:
                    _logger.warning(
                        "[OT BYPASS] allocation_create bypassing hr_holidays_attendance check "
                        "because deductible covers request. employees=%s requested=%s",
                        employees.ids,
                        requested_by_employee,
                    )
                    allocations = super(HrHolidaysAttendanceLeaveAllocation, self).create(vals_list)
                else:
                    raise
            else:
                raise
        is_deduct_extra_hours_flow = bool(self.env.context.get('deduct_extra_hours'))
        for alloc, vals in zip(allocations, vals_list):
            # Skip records already linked by custom OT conversion wizard.
            if vals.get('is_ot_conversion') or vals.get('ot_conversion_input_id') or alloc.ot_conversion_input_id:
                continue
            # Only auto-link allocations created from Odoo "Deduct Extra Hours" flow.
            if not is_deduct_extra_hours_flow:
                continue
            # Only overtime-deductible allocations are relevant.
            if not alloc.employee_id or not alloc.holiday_status_id.overtime_deductible:
                continue

            converted_hours = alloc.number_of_hours_display or alloc.number_of_hours or 0.0
            if converted_hours <= 0:
                continue

            payslip = alloc.employee_id._get_default_ot_conversion_payslip()
            print(212121,payslip)
            if not payslip:
                raise ValidationError(_(
                    'No payslip found for %(employee)s to register OT conversion input.'
                ) % {
                    'employee': alloc.employee_id.display_name,
                })
            if payslip.state == 'cancel':
                raise ValidationError(_(
                    'Payslip %(payslip)s is cancelled, OT conversion input cannot be registered.'
                ) % {
                    'payslip': payslip.display_name,
                })

            conversion_input_type = payslip._get_ot_leave_conversion_input_type()
            conversion_input = self.env['hr.payslip.input'].create({
                'payslip_id': payslip.id,
                'name': _('OT to Annual Leave Conversion'),
                'input_type_id': conversion_input_type.id,
                'hours': converted_hours,
                'amount': 0.0,
            })
            alloc.write({
                'is_ot_conversion': True,
                'ot_conversion_payslip_id': payslip.id,
                'ot_conversion_input_id': conversion_input.id,
            })
            payslip.with_context(skip_reconciled=True).action_reconcile_lateness_no_ot_bank()
        return allocations

    def write(self, vals):
        try:
            return super().write(vals)
        except ValidationError as err:
            self._log_ot_diagnostics(
                employees=self.employee_id,
                vals_list=[vals],
                phase='allocation_write',
                error_message=str(err),
            )
            _logger.warning(
                "[OT DEBUG TRACE] phase=allocation_write error=%s vals=%s ids=%s\n%s",
                str(err),
                vals,
                self.ids,
                traceback.format_exc(),
            )
            raise

    def unlink(self):
        for alloc in self:
            if alloc.is_ot_conversion:
                payslip = alloc.ot_conversion_payslip_id
                input_line = alloc.ot_conversion_input_id

                if payslip and payslip.state != 'draft':
                    raise ValidationError(_(
                        "You cannot delete an OT conversion allocation "
                        "after the payslip is validated."
                    ))

                if input_line:
                    input_line.unlink()

                if payslip:
                    payslip.action_rebuild_ot_wallet()

        return super().unlink()

    def action_refuse(self):
        res = super().action_refuse()

        for alloc in self:
            if alloc.is_ot_conversion:
                payslip = alloc.ot_conversion_payslip_id
                input_line = alloc.ot_conversion_input_id

                if input_line:
                    input_line.unlink()

                if payslip:
                    payslip.action_rebuild_ot_wallet()

        return res
