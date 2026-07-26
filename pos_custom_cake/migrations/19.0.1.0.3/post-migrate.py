# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        UPDATE pos_config
        SET enable_custom_cake = TRUE
        WHERE enable_custom_cake IS NOT TRUE
        """
    )
    _logger.info("Enabled Custom Cake on all POS configurations.")
