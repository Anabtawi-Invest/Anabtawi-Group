from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    employee_number = fields.Char(
        string="Employee Number",
        compute="_compute_employee_number",
        store=True,
        index=True,
        readonly=True,
    )

    @api.depends("employee_ids.employee_number")
    def _compute_employee_number(self):
        for partner in self:
            employee = partner.sudo().employee_ids[:1]
            partner.employee_number = employee.employee_number if employee else False

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        if "employee_number" not in fields_list:
            fields_list.append("employee_number")
        return fields_list
