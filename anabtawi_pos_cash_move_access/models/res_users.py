from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _has_cash_move_permission(self):
        self.ensure_one()
        if self.has_group("anabtawi_pos_cash_move_access.group_pos_cash_in_out"):
            return True
        return super()._has_cash_move_permission()
