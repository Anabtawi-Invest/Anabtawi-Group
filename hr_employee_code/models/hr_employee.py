from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    employee_number = fields.Char(string="Employee Number")

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees._sync_partner_employee_number()
        return employees

    def write(self, vals):
        res = super().write(vals)
        if any(field in vals for field in ("employee_number", "work_contact_id", "user_id")):
            self._sync_partner_employee_number()
        return res

    def _sync_partner_employee_number(self):
        for employee in self:
            partners = (
                employee.sudo().work_contact_id | employee.sudo().user_partner_id
            ).exists()
            for partner in partners:
                partner.with_company(employee.company_id)._compute_employee_number()
