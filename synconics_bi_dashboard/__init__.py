from . import models
from . import wizard


def pre_init_hook(env):
    """Clear the broken module record left after the folder rename."""
    old_module = env["ir.module.module"].sudo().search(
        [("name", "=", "synconics_bi_dashboard_UPDATED")]
    )
    if old_module:
        old_module.write({"state": "uninstalled"})


def post_init_hook(env):
    dashboards = env["dashboard.dashboard"].sudo().search([("created_menu_id", "=", False)])
    if dashboards:
        dashboards.create_update_menu()


def uninstall_hook(env):
    dashboards = env["dashboard.dashboard"].sudo().search([])
    dashboards.created_action_id.unlink()
    dashboards.created_menu_id.unlink()
