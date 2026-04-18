from odoo import fields, models


class HrAttendanceOvertimeRule(models.Model):
    _inherit = "hr.attendance.overtime.rule"

    work_entry_type_id = fields.Many2one(
        "hr.work.entry.type",
        string="Work Entry Type",
        domain=[("is_leave", "=", False)],
        help="Its rate is used when converting overtime into credited extra hours.",
    )

    def _extra_overtime_vals(self):
        res = super()._extra_overtime_vals()
        paid_rules = self.filtered(lambda rule: rule.paid and rule.work_entry_type_id)
        if not paid_rules:
            res["work_entry_type_id"] = False
            return res

        # If multiple paid rules apply to the same overtime line, keep the work
        # entry type of the strongest rate so the credited balance stays stable.
        selected_rule = max(paid_rules, key=lambda rule: (rule.amount_rate, rule.sequence))
        res["work_entry_type_id"] = selected_rule.work_entry_type_id.id
        return res
