# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    must_change_password = fields.Boolean(
        string='Must Change Password',
        default=True,
        help='When enabled, the user must set a new password on next login. '
             'Set to False automatically after they change it.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('must_change_password', True)
        return super().create(vals_list)

    def write(self, vals):
        if (
            'password' in vals
            and not self.env.context.get('auth_force_password_change_done')
            and vals.get('must_change_password') is not False
        ):
            others = self.filtered(lambda user: user.id != self.env.uid)
            if others:
                vals = dict(vals, must_change_password=True)
        return super().write(vals)

    def must_reset_password_on_login(self):
        self.ensure_one()
        return self.must_change_password or not self.log_ids
