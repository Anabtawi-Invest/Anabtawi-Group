# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    is_onsite_order = fields.Boolean(
        string="On-Site Order",
        default=False,
        help="Set from the POS Yes/No popup. Yes skips pledge and uses site-service logic.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        if "is_onsite_order" not in fields_list:
            fields_list.append("is_onsite_order")
        return fields_list

    def _include_in_pledge_closing_summary(self):
        self.ensure_one()
        if self.is_onsite_order:
            return False
        return super()._include_in_pledge_closing_summary()

    def _is_site_service_pledge_blocked(self):
        self.ensure_one()
        if self.is_onsite_order:
            return True
        parent = super()
        method = getattr(parent, "_is_site_service_pledge_blocked", None)
        if callable(method):
            return method()
        return False
