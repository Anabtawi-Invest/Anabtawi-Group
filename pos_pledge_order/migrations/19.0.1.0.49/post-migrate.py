# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Ensure cutting_service_product_id column exists on site service menu."""
    cr.execute(
        """
        SELECT 1
          FROM information_schema.tables
         WHERE table_name = 'pos_site_service_menu'
         LIMIT 1
        """
    )
    if not cr.fetchone():
        return

    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'pos_site_service_menu'
           AND column_name = 'cutting_service_product_id'
         LIMIT 1
        """
    )
    if cr.fetchone():
        return

    cr.execute(
        """
        ALTER TABLE pos_site_service_menu
            ADD COLUMN cutting_service_product_id INTEGER
        """
    )
    _logger.info("[SITE_SERVICE] Added cutting_service_product_id column.")
