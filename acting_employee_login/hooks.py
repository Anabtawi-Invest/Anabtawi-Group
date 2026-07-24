# -*- coding: utf-8 -*-

def _post_init_hook(env):
    icp = env['ir.config_parameter'].sudo()
    if not icp.get_param('acting_employee_login.enabled_modules'):
        icp.set_param('acting_employee_login.enabled_modules', 'stock,hr')
