# -*- coding: utf-8 -*-
from odoo import models
import logging

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _load_pos_data_fields(self, config_id):
        """Add custom pledge fields to POS data loading"""
        _logger.info("[PLEDGE] _load_pos_data_fields called for product.product")
        
        fields = super()._load_pos_data_fields(config_id)
        
        # Add our custom fields
        fields.extend([
            'is_pledge_product',
            'pledge_amount',
            'is_employee_service',
            'is_delivery_product',
        ])
        
        _logger.info("[PLEDGE] Added pledge fields to product loading: %s", fields[-4:])
        
        return fields
