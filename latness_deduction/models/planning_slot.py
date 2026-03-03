from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta


class PlanningSlot(models.Model):
    _inherit = 'planning.slot'

    convert_ot_to_leave = fields.Boolean(
        string="Convert OT to Time Off",
        copy=False,
    )

    ot_balance_display = fields.Float(
        string="Available OT (hrs)",
        compute="_compute_ot_balance_display",
        readonly=True,
    )

    ot_leave_id = fields.Many2one(
        'hr.leave',
        string="Generated Time Off",
        readonly=True,
        copy=False,
    )

    # =========================================================
    # Compute Available OT from last payslip
    # =========================================================
    @api.depends('resource_id')
    def _compute_ot_balance_display(self):
        Payslip = self.env['hr.payslip']
        for slot in self:
            slot.ot_balance_display = 0.0
            employee = slot.resource_id.employee_id
            if not employee:
                continue

            last_payslip = Payslip.search([
                ('employee_id', '=', employee.id),
                ('state', '!=', 'cancel'),
            ], order='date_to desc, id desc', limit=1)

            if last_payslip:
                slot.ot_balance_display = (
                    last_payslip._get_ot_balance_after_value() or 0.0
                )

    # =========================================================
    # Override Publish Button
    # =========================================================
    def action_send(self):
        res = super().action_send()
        self._handle_ot_conversion()
        return res

    # =========================================================
    # Core OT → Time Off Logic
    # =========================================================
    def _handle_ot_conversion(self):
        Leave = self.env['hr.leave']
        Payslip = self.env['hr.payslip']
        PayslipInput = self.env['hr.payslip.input']

        for slot in self:

            # Execute only if checkbox is checked
            if not slot.convert_ot_to_leave:
                continue

            # Prevent duplicate conversion
            if slot.ot_leave_id:
                raise ValidationError(_("Time Off already created for this shift."))

            hours = slot.allocated_hours or 0.0
            if hours <= 0:
                raise ValidationError(_("Allocated hours must be greater than 0."))

            employee = slot.resource_id.employee_id
            if not employee:
                raise ValidationError(_("No employee linked to this shift."))

            # Get last payslip
            last_payslip = Payslip.search([
                ('employee_id', '=', employee.id),
                ('state', '!=', 'cancel'),
            ], order='date_to desc, id desc', limit=1)

            if not last_payslip:
                raise ValidationError(_("No payslip found for this employee."))

            # Check available OT
            available = last_payslip._get_ot_balance_after_value()
            if hours > available + 1e-6:
                raise ValidationError(_(
                    "Allocated hours (%.2f) exceed available OT balance (%.2f)."
                ) % (hours, available))

            # Get Leave Type
            leave_type = last_payslip._get_configured_annual_leave_type()
            if not leave_type:
                raise ValidationError(_("Annual Leave Type not configured."))

            # =================================================
            # 1️⃣ Create Payslip Input (Deduct OT)
            # =================================================
            conversion_input_type = last_payslip._get_ot_leave_conversion_input_type()

            PayslipInput.create({
                'payslip_id': last_payslip.id,
                'name': _('OT to Time Off Conversion'),
                'input_type_id': conversion_input_type.id,
                'hours': hours,
                'amount': 0.0,
            })

            # =================================================
            # 2️⃣ Create Time Off
            # =================================================
            leave_date = fields.Date.to_date(slot.start_datetime)

            hour_from = 8.0
            hour_to = hour_from + hours

            leave = Leave.sudo().create({
                'name': _('OT Conversion from Published Shift'),
                'employee_id': employee.id,
                'holiday_status_id': leave_type.id,
                'request_date_from': leave_date,
                'request_date_to': leave_date,
                'request_unit_hours': True,
                'request_hour_from': hour_from,
                'request_hour_to': hour_to,
            })

            if hasattr(leave, 'action_approve'):
                leave.sudo().action_approve(check_state=False)

            if hasattr(leave, 'action_validate'):
                leave.sudo().action_validate()

            # =================================================
            # 3️⃣ Rebuild OT Wallet
            # =================================================
            last_payslip.action_rebuild_ot_wallet()

            # =================================================
            # 4️⃣ Convert Planning Slot into "Time Off"
            # =================================================
            slot.write({
                'name': _('Time Off'),
                'color': 1,
                'allocated_hours': hours,
                'convert_ot_to_leave': False,
                'ot_leave_id': leave.id,
            })