from odoo import models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def _load_pos_data_read(self, records, config):
        read_records = super()._load_pos_data_read(records, config)
        for employee in read_records:
            user_id = employee.get("user_id")
            if user_id:
                user = self.env["res.users"].browse(user_id)
                employee["_has_cash_move_perm"] = user._has_cash_move_permission()
            else:
                employee["_has_cash_move_perm"] = False
        return read_records
