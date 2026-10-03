# -*- coding: utf-8 -*-
from odoo import fields, models


class CrmTeam(models.Model):
    _inherit = 'crm.team'

    use_logistics_shipping_request = fields.Boolean(
        string='Enable Shipping Cost Requests',
        default=False,
        help='Check this option if this sales team (e.g. Export Sales) can request logistics shipping costs.',
    )
