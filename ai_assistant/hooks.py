# -*- coding: utf-8 -*-

from .services.config import PARAM_ENABLED, PARAM_PROVIDER, PROVIDER_MOCK


def post_init_hook(env):
    """Set default config parameters on first install only (never overwrite)."""
    icp = env["ir.config_parameter"].sudo()
    defaults = {
        PARAM_ENABLED: "True",
        PARAM_PROVIDER: PROVIDER_MOCK,
    }
    for key, value in defaults.items():
        if not icp.search_count([("key", "=", key)]):
            icp.set_param(key, value)
