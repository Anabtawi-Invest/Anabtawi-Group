# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Quantity ranges no longer use service_type='none'."""
    cr.execute(
        """
        SELECT 1
          FROM information_schema.tables
         WHERE table_name = 'pos_onsite_price_range'
         LIMIT 1
        """
    )
    if not cr.fetchone():
        return

    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'pos_onsite_price_range'
           AND column_name = 'service_type'
         LIMIT 1
        """
    )
    if not cr.fetchone():
        return

    cr.execute(
        """
        DELETE FROM pos_onsite_price_range
         WHERE service_type = 'none'
        """
    )
    deleted = cr.rowcount
    if deleted:
        _logger.info(
            "[ONSITE] Removed %s quantity range(s) with service_type=none.",
            deleted,
        )
