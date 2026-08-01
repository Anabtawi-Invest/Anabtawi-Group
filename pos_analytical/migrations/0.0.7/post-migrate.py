import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        DELETE FROM ir_asset
         WHERE path LIKE 'sh_pos_analytic_tags/%'
           AND COALESCE(directive, 'append') != 'remove'
        """
    )
    cr.execute(
        """
        UPDATE ir_module_module
           SET state = 'installed'
         WHERE name = 'sh_pos_analytic_tags'
           AND state NOT IN ('installed', 'to upgrade', 'to install')
        """
    )
    _logger.info(
        "pos_analytical 0.0.7: ensured sh_pos_analytic_tags stub is installed "
        "and removed legacy asset includes."
    )
