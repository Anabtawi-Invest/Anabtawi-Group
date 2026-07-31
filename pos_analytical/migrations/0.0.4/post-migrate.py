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
        SELECT id FROM ir_module_module
         WHERE name = 'sh_pos_analytic_tags'
           AND state = 'installed'
        """
    )
    if cr.fetchone():
        cr.execute(
            """
            UPDATE ir_module_module
               SET state = 'uninstalled'
             WHERE name = 'sh_pos_analytic_tags'
            """
        )
        _logger.info(
            "Marked obsolete module sh_pos_analytic_tags as uninstalled "
            "(replaced by pos_analytical)."
        )
