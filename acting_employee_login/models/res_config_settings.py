# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    acting_employee_module_ids = fields.Many2many(
        'ir.module.module',
        string='Acting Employee Chatter Modules',
        domain="[('state', '=', 'installed')]",
        help='Chatter messages on documents from these modules will show '
             'the acting employee name beside the username.',
    )

    def set_values(self):
        super().set_values()
        names = ','.join(self.acting_employee_module_ids.mapped('name'))
        self.env['ir.config_parameter'].sudo().set_param(
            'acting_employee_login.enabled_modules', names
        )

    @api.model
    def get_values(self):
        res = super().get_values()
        names = self.env['ir.config_parameter'].sudo().get_param(
            'acting_employee_login.enabled_modules', ''
        )
        module_names = [name.strip() for name in names.split(',') if name.strip()]
        modules = self.env['ir.module.module']
        if module_names:
            modules = modules.search([
                ('name', 'in', module_names),
                ('state', '=', 'installed'),
            ])
        res['acting_employee_module_ids'] = [(6, 0, modules.ids)]
        return res
