# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    must_change_password = fields.Boolean(
        string='Must Change Password',
        default=False,
        help='When enabled, the user must set a new password on next login.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('must_change_password', True)
        return super().create(vals_list)

    def must_reset_password_on_login(self):
        self.ensure_one()
        return self.must_change_password or not self.log_ids
