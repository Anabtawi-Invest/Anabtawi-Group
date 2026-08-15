from odoo import models

RESTRICT_QTY_GROUP = "pos_restrict_qty_change.group_pos_restrict_qty_change"


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def _load_pos_data_read(self, records, config):
        read_records = super()._load_pos_data_read(records, config)
        for employee in read_records:
            user_id = employee.get("user_id")
            if isinstance(user_id, (list, tuple)):
                user_id = user_id[0] if user_id else False
            if user_id:
                user = self.env["res.users"].browse(user_id)
                employee["_restrict_pos_qty_change"] = user.has_group(RESTRICT_QTY_GROUP)
            else:
                employee["_restrict_pos_qty_change"] = False
        return read_records
