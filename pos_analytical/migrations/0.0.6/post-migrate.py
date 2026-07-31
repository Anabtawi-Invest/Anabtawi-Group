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
        UPDATE ir_asset
           SET sequence = 9999
         WHERE path = 'sh_pos_analytic_tags/static/src/overrides/models.js'
           AND directive = 'remove'
        """
    )
    _logger.info(
        "pos_analytical 0.0.6: cleaned legacy sh_pos_analytic_tags asset includes "
        "and fixed remove directive ordering."
    )
