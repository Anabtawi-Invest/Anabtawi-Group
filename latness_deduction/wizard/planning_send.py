# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class PlanningSend(models.TransientModel):
    _inherit = 'planning.send'

    def action_send(self):
        self.ensure_one()
        if self.include_unassigned:
            slot_to_send = self.slot_ids.filtered(
                lambda s: not s.employee_id or s.employee_id in self.employee_ids
            )
        else:
            slot_to_send = self.slot_ids.filtered(
                lambda s: s.employee_id in self.employee_ids
            )
        res = super().action_send()
        # Apply same OT conversion as single-slot "Send": run _handle_ot_conversion
        # on slots that have "Convert OT to Time Off" checked (Send schedule flow).
        if res and slot_to_send:
            slots_to_convert = slot_to_send.filtered('convert_ot_to_leave')
            if slots_to_convert:
                slots_to_convert._handle_ot_conversion()
        return res
