# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models

class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _load_pos_data_models(self, config):
        models_to_load = super()._load_pos_data_models(config)
        if "pos.predefined.discount" not in models_to_load:
            models_to_load.append("pos.predefined.discount")
        return models_to_load

