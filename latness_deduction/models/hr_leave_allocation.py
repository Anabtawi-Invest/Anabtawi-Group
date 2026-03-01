from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

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

    @api.model_create_multi
    def create(self, vals_list):
        allocations = super().create(vals_list)
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
