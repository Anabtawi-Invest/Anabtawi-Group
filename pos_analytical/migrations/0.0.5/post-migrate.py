import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        DELETE FROM ir_asset
         WHERE path LIKE 'sh_pos_analytic_tags/%'
           AND directive != 'remove'
        """
    )
    cr.execute(
        """
        UPDATE ir_module_module
           SET state = 'uninstalled'
         WHERE name = 'sh_pos_analytic_tags'
           AND state = 'installed'
        """
    )
    _logger.info(
        "pos_analytical 0.0.5: cleaned legacy sh_pos_analytic_tags asset includes."
    )
