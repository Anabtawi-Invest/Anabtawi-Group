# -*- coding: utf-8 -*-
################################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2025-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author: Sreerag PM (<https://www.cybrosys.com>)
#
#    This program is free software: you can modify
#    it under the terms of the GNU Affero General Public License (AGPL) as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
################################################################################
from odoo import api, models


class PosSession(models.Model):
    """Extend POS data loading for Odoo 19.

    Odoo 19 uses `_load_pos_data_models()` + each model's `_load_pos_data_fields()`
    to decide what the POS UI loads at startup.
    """
    _inherit = "pos.session"

    @api.model
    def _load_pos_data_models(self, config):
        """Add our `pos.receipt` model to the POS payload."""
        models_to_load = super()._load_pos_data_models(config)
        if "pos.receipt" not in models_to_load:
            models_to_load.append("pos.receipt")
        return models_to_load
