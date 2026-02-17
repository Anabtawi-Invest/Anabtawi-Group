# Copyright (C) Softhealer Technologies.
# Part of Softhealer Technologies.

from odoo import models, fields, api

class ResConfigSettiongsInhert(models.TransientModel):
    """Inherits res.config.settings to manage Point of Sale configurations."""
    _inherit = "res.config.settings"

    pos_sh_analytic_account = fields.Many2one(related="pos_config_id.sh_analytic_account", readonly=False)

    @api.model
    def _load_pos_data_domain(self, data):
        """This method is a hook to be inherited by other modules.
        It is meant to return a domain to filter pos.config records.
        """
        return []

    @api.model
    def _load_pos_data_fields(self, config_id):
        """This method is a hook to be inherited by other modules.
        It is meant to return a list of fields to be loaded for pos.config records.
        """
        return []

    def _load_pos_data(self, data):
        """This method loads data for the Point of Sale configuration.
        It uses the domain and fields returned by the hook methods.
        """
        domain = self._load_pos_data_domain(data)
        fields = self._load_pos_data_fields(data['pos.config']['data'][0]['id'])
        return {
            'data': self.search_read(domain, fields, load=False) if domain is not False else [],
            'fields': fields,
        }
