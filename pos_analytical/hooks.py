import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    _cleanup_legacy_analytic_assets(env)


def _cleanup_legacy_analytic_assets(env):
    env.cr.execute(
        """
        DELETE FROM ir_asset
         WHERE path LIKE 'sh_pos_analytic_tags/%'
        """
    )
    if env.cr.rowcount:
        _logger.info(
            "pos_analytical: removed %s legacy sh_pos_analytic_tags asset record(s).",
            env.cr.rowcount,
        )
    env.registry.clear_cache('assets')
