from odoo import _, models


class HrDepartment(models.Model):
    _inherit = "hr.department"

    def _compute_total_employee(self):
        all_departments = self.get_children_department_ids()
        emp_data = self.env["hr.employee"].sudo()._read_group(
            [
                ("department_id", "in", all_departments.ids),
                ("company_id", "in", self.env.companies.ids),
            ],
            ["department_id"],
            ["__count"],
        )
        count_by_department = {department.id: count for department, count in emp_data}
        children_by_root = {
            department.id: self.env["hr.department"].search([("id", "child_of", department.id)]).ids
            for department in self
        }
        for department in self:
            department.total_employee = sum(
                count_by_department.get(child_id, 0)
                for child_id in children_by_root.get(department.id, [])
            )

    def action_employee_from_department(self):
        self.ensure_one()
        action = super().action_employee_from_department()
        action["domain"] = [("department_id", "child_of", self.ids)]
        action["context"] = {
            **action.get("context", {}),
            "default_department_id": self.id,
            "search_default_group_department": 1,
            "expand": 1,
        }
        action["name"] = _("Employees")
        return action
