import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    _cleanup_legacy_analytic_module(env)


def _cleanup_legacy_analytic_module(env):
    env.cr.execute(
        """
        DELETE FROM ir_asset
         WHERE path LIKE 'sh_pos_analytic_tags/%'
        """
    )
    ghost_module = env['ir.module.module'].sudo().search([
        ('name', '=', 'sh_pos_analytic_tags'),
    ], limit=1)
    if ghost_module and ghost_module.state == 'installed':
        ghost_module.write({'state': 'uninstalled'})
        _logger.info(
            "Marked obsolete module sh_pos_analytic_tags as uninstalled "
            "(replaced by pos_analytical)."
        )
    env.registry.clear_cache('assets')
