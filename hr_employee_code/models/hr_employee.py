from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    employee_number = fields.Char(string="Employee Number")

    @api.constrains("employee_number", "company_id")
    def _check_unique_employee_number(self):
        for employee in self:
            number = (employee.employee_number or "").strip()
            if not number:
                continue
            domain = [
                ("id", "!=", employee.id),
                ("employee_number", "=", number),
            ]
            if employee.company_id:
                domain.append(("company_id", "=", employee.company_id.id))
            else:
                domain.append(("company_id", "=", False))
            duplicate = self.sudo().with_context(active_test=False).search(domain, limit=1)
            if duplicate:
                company_name = employee.company_id.name if employee.company_id else _("Undefined Company")
                raise ValidationError(
                    _(
                        "الرقم الوظيفي '%(number)s' موجود مسبقاً للموظف (%(duplicate_name)s) في شركة (%(company)s).\n"
                        "يجب أن يكون الرقم الوظيفي فريداً داخل نفس الشركة."
                    )
                    % {
                        "number": number,
                        "duplicate_name": duplicate.name,
                        "company": company_name,
                    }
                )

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

