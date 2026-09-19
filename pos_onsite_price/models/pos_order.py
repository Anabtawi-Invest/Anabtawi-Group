# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    is_onsite_order = fields.Boolean(
        string="On-Site Order",
        default=False,
        help="True when the cashier chose On Site or Cutting (skips pledge).",
    )
    onsite_service_type = fields.Selection(
        selection=[
            ("on_site", "On Site"),
            ("cutting", "Cutting"),
            ("none", "None"),
        ],
        string="On-Site Service Type",
        help="Cashier choice from the on-site pricing popup.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        # Core pos.order returns [] meaning "load all fields". Keep that so
        # inherited fields (e.g. sh_pos_order_analytic_account) stay available.
        if not fields_list:
            return fields_list
        for fname in ("is_onsite_order", "onsite_service_type"):
            if fname not in fields_list:
                fields_list.append(fname)
        return fields_list

    def _include_in_pledge_closing_summary(self):
        self.ensure_one()
        if self.is_onsite_order or self.onsite_service_type in ("on_site", "cutting"):
            return False
        return super()._include_in_pledge_closing_summary()

    def _is_site_service_pledge_blocked(self):
        self.ensure_one()
        if self.is_onsite_order or self.onsite_service_type in ("on_site", "cutting"):
            return True
        parent = super()
        method = getattr(parent, "_is_site_service_pledge_blocked", None)
        if callable(method):
            return method()
        return False
