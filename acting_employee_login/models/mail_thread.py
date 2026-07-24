# -*- coding: utf-8 -*-

from odoo import models


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _message_create(self, values_list):
        mail_message = self.env['mail.message']
        enriched_values_list = []
        for values in values_list:
            vals = dict(values)
            if not (
                vals.get('acting_employee_name')
                or vals.get('acting_branch_name')
            ):
                model_name = vals.get('model') or self._name
                acting_vals = mail_message._get_acting_identity_vals(model_name)
                if acting_vals:
                    vals.update(acting_vals)
            enriched_values_list.append(vals)
        return super()._message_create(enriched_values_list)
