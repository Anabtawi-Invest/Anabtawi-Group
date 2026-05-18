from odoo import models, fields, api, _
from odoo.exceptions import UserError


class OvertimeRefuseWizard(models.TransientModel):
    _name = 'overtime.refuse.wizard'
    _description = 'Refuse Overtime Request Wizard'

    overtime_request_id = fields.Many2one(
        'attendance.overtime.request',
        string='Overtime Request',
        required=True,
    )
    refusal_reason = fields.Text(
        string='Refusal Reason',
        required=True,
    )

    def action_refuse(self):
        self.ensure_one()
        req = self.overtime_request_id
        if req.state != 'submitted':
            raise UserError(_('Only submitted requests can be refused.'))
        req.write({
            'state': 'refused',
            'refusal_reason': self.refusal_reason,
        })
        return {'type': 'ir.actions.act_window_close'}
