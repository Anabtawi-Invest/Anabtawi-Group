import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

LEGACY_SH_POS_ASSET_PREFIX = 'sh_pos_analytic_tags/'


class IrAsset(models.Model):
    _inherit = 'ir.asset'

    @api.model
    def _register_hook(self):
        super()._register_hook()
        if not self.env.registry.ready:
            return
        self.env.cr.execute(
            """
            DELETE FROM ir_asset
             WHERE path LIKE %s
               AND COALESCE(directive, 'append') != 'remove'
            """,
            (LEGACY_SH_POS_ASSET_PREFIX + '%',),
        )
        if self.env.cr.rowcount:
            _logger.info(
                "pos_analytical: removed %s legacy sh_pos_analytic_tags asset record(s).",
                self.env.cr.rowcount,
            )
            self.env.registry.clear_cache('assets')
