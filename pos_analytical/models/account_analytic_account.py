# Copyright (C) Softhealer Technologies.
# Part of Softhealer Technologies.


from odoo import _, api, models


class AccountAnalyticAccount(models.Model):
    """Inherits account.analytic.account to add POS data loading capabilities."""
    _inherit = 'account.analytic.account'

    @api.model
    def _load_pos_data_search_read(self, data, config):
        """Search and return records to be loaded in the POS"""
        if not config:
            raise ValueError("config must be provided to search for PoS data.")

        domain = self._server_date_to_domain(self._load_pos_data_domain(data, config))
        if domain is False:
            return []

        records = self.search(domain)
        return self._load_pos_data_read(records, config)

    @api.model
    def _load_pos_data_domain(self, data, config):
        """
        Returns the domain for loading POS data.

        Args:
            data (dict): The data dictionary.
            config (dict): The POS configuration.

        Returns:
            list: An empty list, as this is a placeholder.
        """
        return []

    @api.model
    def _server_date_to_domain(self, domain):
        """Optionally restrict the domain to records modified after the last server sync"""
        return domain

    @api.model
    def _load_pos_data_read(self, records, config):
        """Read specific fields from the given records"""
        if not config:
            raise ValueError("config must be provided to read PoS data.")

        fields = self._load_pos_data_fields(config)
        records = records.read(fields, load=False)
        return records or []

    def _unrelevant_records(self, config):
        return self.filtered(lambda record: not record.active).ids

    @api.model
    def _load_pos_data_fields(self, config):
        """Return the list of fields to be loaded"""
        return []
