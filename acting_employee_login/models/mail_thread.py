# -*- coding: utf-8 -*-

import logging

from odoo import models

from ..acting_log import _session_snapshot, log_chatter_debug

_logger = logging.getLogger(__name__)


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _message_create(self, values_list):
        mail_message = self.env['mail.message']
        enriched_values_list = []
        for values in values_list:
            vals = dict(values)
            model_name = vals.get('model') or self._name
            if not (
                vals.get('acting_employee_name')
                or vals.get('acting_branch_name')
            ):
                acting_vals = mail_message._get_acting_identity_vals(model_name)
                if acting_vals:
                    vals.update(acting_vals)
                    if model_name == 'stock.picking':
                        log_chatter_debug(
                            'thread_message_create_enriched',
                            thread_model=self._name,
                            message_model=model_name,
                            res_id=vals.get('res_id'),
                            acting_vals=acting_vals,
                        )
                elif model_name == 'stock.picking':
                    log_chatter_debug(
                        'thread_message_create_not_enriched',
                        thread_model=self._name,
                        message_model=model_name,
                        res_id=vals.get('res_id'),
                        session=_session_snapshot(),
                    )
            enriched_values_list.append(vals)
        return super()._message_create(enriched_values_list)
