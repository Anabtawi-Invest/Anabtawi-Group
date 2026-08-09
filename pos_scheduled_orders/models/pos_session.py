# -*- coding: utf-8 -*-
from odoo import models


class PosSession(models.Model):
    _inherit = "pos.session"

    def _loader_params_res_partner(self):
        result = super()._loader_params_res_partner()
        fields_list = result.get("search_params", {}).get("fields", [])
        extra_partner_fields = [
            "building_apt",
            "mobile",
            "phone",
            "street",
            "city",
            "zip",
        ]
        for field in extra_partner_fields:
            if field not in fields_list:
                fields_list.append(field)
        return result

    def _pos_ui_models_to_load(self):
        models_to_load = super()._pos_ui_models_to_load()
        return models_to_load
