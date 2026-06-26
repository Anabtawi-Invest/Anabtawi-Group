# -*- coding: utf-8 -*-

import secrets

from . import models
from . import controllers


def post_init_hook(env):
    icp = env['ir.config_parameter'].sudo()
    if not icp.get_param('anabtawi_mobile.token_pepper'):
        icp.set_param('anabtawi_mobile.token_pepper', secrets.token_hex(32))
