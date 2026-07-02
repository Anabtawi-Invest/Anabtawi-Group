import secrets
from . import controllers
from . import models


def post_init_hook(env):
    icp = env["ir.config_parameter"].sudo()
    if not icp.get_param("anabtawi_mobile.token_pepper"):
        icp.set_param("anabtawi_mobile.token_pepper", secrets.token_hex(32))

