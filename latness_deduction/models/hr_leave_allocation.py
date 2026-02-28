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

    @api.depends('employee_id', 'date_from')
    def _compute_number_of_day_converted(self):
        payslip_model = self.env['hr.payslip']
        print(6666)
        for alloc in self:
            alloc.number_of_day_converted = 0.0
            if not alloc.employee_id:
                continue

            last_payslip = payslip_model.search(
                [('employee_id', '=', alloc.employee_id.id)],
                order='date_to desc, id desc',
                limit=1,
            )
            print(7777,last_payslip)
            if not last_payslip:
                continue

            self.number_of_day_converted = last_payslip.ot_balance_after or 0.0
            print(555,self.number_of_day_converted)

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