import secrets

from . import controllers
from . import models


def post_init_hook(env):
    parameters = env["ir.config_parameter"].sudo()
    if not parameters.get_param("anabtawi_mobile.token_pepper"):
        parameters.set_param("anabtawi_mobile.token_pepper", secrets.token_hex(32))
