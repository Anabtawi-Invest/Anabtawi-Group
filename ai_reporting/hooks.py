# Part of Odoo. See LICENSE file for full copyright and licensing details.


def post_init_hook(env):
    env["ai.reporting.discovery.service"].refresh_metadata(scan_addons=True, build_templates=False)
