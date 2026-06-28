from . import models
from . import wizard


def post_init_hook(env):
    dashboards = env["dashboard.dashboard"].sudo().search([("created_menu_id", "=", False)])
    if dashboards:
        dashboards.create_update_menu()


def uninstall_hook(env):
    dashboards = env["dashboard.dashboard"].sudo().search([])
    dashboards.created_action_id.unlink()
    dashboards.created_menu_id.unlink()
