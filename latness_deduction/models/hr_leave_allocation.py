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

    def unlink(self):
        print(111111)
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
        print(22222)
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