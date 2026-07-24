# -*- coding: utf-8 -*-

import logging

from odoo import models

from ..acting_log import _session_snapshot, log_chatter_debug

_logger = logging.getLogger(__name__)

PREcommit_IDENTITY_KEY = 'acting_employee_login.identity'


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _acting_login_get_identity_vals(self):
        return self.env['mail.message']._get_acting_identity_vals(self._name)

    def _acting_login_stash_identity(self):
        acting_vals = self._acting_login_get_identity_vals()
        if acting_vals:
            self.env.cr.precommit.data[PREcommit_IDENTITY_KEY] = acting_vals
        return acting_vals

    def _acting_login_get_stashed_identity(self):
        return dict(self.env.cr.precommit.data.get(PREcommit_IDENTITY_KEY) or {})

    def write(self, vals):
        if not self.env.context.get('tracking_disable'):
            self._acting_login_stash_identity()
        return super().write(vals)

    def message_post(self, **kwargs):
        if not (
            kwargs.get('acting_employee_name')
            or kwargs.get('acting_branch_name')
        ):
            acting_vals = (
                self._acting_login_get_identity_vals()
                or self._acting_login_get_stashed_identity()
            )
            if acting_vals:
                kwargs.update(acting_vals)
                if self._name == 'stock.picking':
                    log_chatter_debug(
                        'message_post_identity',
                        model=self._name,
                        res_ids=self.ids,
                        acting_vals=acting_vals,
                    )
        return super().message_post(**kwargs)

    def _message_log_batch(self, bodies, subject=False, author_id=None, email_from=None,
                           message_type='notification', partner_ids=False,
                           attachment_ids=False, tracking_value_ids=False):
        acting_vals = (
            self._acting_login_get_identity_vals()
            or self._acting_login_get_stashed_identity()
        )
        if acting_vals and self._name == 'stock.picking':
            log_chatter_debug(
                'message_log_batch_identity',
                model=self._name,
                res_ids=self.ids,
                acting_vals=acting_vals,
            )
        # Inject into base values by temporarily patching _message_create input.
        result = super()._message_log_batch(
            bodies,
            subject=subject,
            author_id=author_id,
            email_from=email_from,
            message_type=message_type,
            partner_ids=partner_ids,
            attachment_ids=attachment_ids,
            tracking_value_ids=tracking_value_ids,
        )
        if acting_vals and result:
            to_update = result.filtered(
                lambda msg: not msg.acting_branch_name and not msg.acting_employee_name
            )
            if to_update:
                to_update.write(acting_vals)
        return result

    def _message_create(self, values_list):
        mail_message = self.env['mail.message']
        stashed = self._acting_login_get_stashed_identity()
        enriched_values_list = []
        for values in values_list:
            vals = dict(values)
            if not (
                vals.get('acting_employee_name')
                or vals.get('acting_branch_name')
            ):
                model_name = vals.get('model') or self._name
                acting_vals = (
                    mail_message._get_acting_identity_vals(model_name)
                    or stashed
                )
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
                        stashed=stashed,
                    )
            enriched_values_list.append(vals)
        return super()._message_create(enriched_values_list)
