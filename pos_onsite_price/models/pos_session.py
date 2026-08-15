# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

ONSITE_POS_MODELS = (
    "pos.onsite.price.menu",
    "pos.onsite.price.range",
    "pos.onsite.price.product",
)


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _load_pos_data_models(self, config):
        models_to_load = super()._load_pos_data_models(config)
        for model_name in ONSITE_POS_MODELS:
            if model_name not in models_to_load:
                models_to_load.append(model_name)
                _logger.info(
                    "[ONSITE] Registered POS data model %s for config id=%s",
                    model_name,
                    getattr(config, "id", config),
                )
        return models_to_load
