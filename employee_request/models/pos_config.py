# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    employee_pricelist_id = fields.Many2one(
        comodel_name="product.pricelist",
        string="Employee Pricelist",
        help="Pricelist to use for employee-related pricing in this Point of Sale.",
        domain="['|', ('company_id', '=', company_id), ('company_id', '=', False)]",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        """Expose employee_pricelist_id to the POS frontend.

        Important: when `super()` returns an empty list, PoS treats it as "load all fields".
        In that case, we must keep it empty to avoid breaking core PoS loading.
        """
        fields_to_load = super()._load_pos_data_fields(config)
        if not fields_to_load:
            return fields_to_load
        if "employee_pricelist_id" not in fields_to_load:
            fields_to_load.append("employee_pricelist_id")
        return fields_to_load

