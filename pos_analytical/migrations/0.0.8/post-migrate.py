import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        DELETE FROM ir_asset
         WHERE path LIKE 'sh_pos_analytic_tags/%'
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
        "pos_analytical 0.0.8: removed all legacy sh_pos_analytic_tags asset "
        "records (including broken remove directives)."
    )
