# -*- coding: utf-8 -*-
from odoo import models
import logging

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = 'pos.session'
    
    # Note: Product fields are now loaded via product_product.py _load_pos_data_fields method
