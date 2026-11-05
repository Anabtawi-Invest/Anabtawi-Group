# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AnabtawiEmployeeAppLeaveType(models.Model):
    _name = "anabtawi.employee.app.leave.type"
    _description = "Time off type shown in the Employee Portal / App"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        ondelete="cascade",
        default=lambda self: self.env.company,
        index=True,
    )
    leave_type_id = fields.Many2one(
        "hr.leave.type",
        string="Time Off Type",
        required=True,
        ondelete="cascade",
    )

    _company_leave_type_unique = models.Constraint(
        "UNIQUE(company_id, leave_type_id)",
        "This time off type is already selected for the Employee Portal / App.",
    )


class ResCompany(models.Model):
    _inherit = "res.company"

    employee_app_leave_type_ids = fields.One2many(
        "anabtawi.employee.app.leave.type",
        "company_id",
        string="Portal / App Time Off Types",
    )

    def _anabtawi_configured_leave_types(self):
        """Active leave types selected for this company (portal + employee app)."""
        self.ensure_one()
        selected = self.env["hr.leave.type"].browse()
        for line in self.employee_app_leave_type_ids.sorted(key=lambda rec: (rec.sequence, rec.id)):
            leave_type = line.leave_type_id
            if leave_type and leave_type.active and leave_type not in selected:
                selected |= leave_type
        return selected

    @api.model
    def _anabtawi_leave_types_for_employee(self, employee):
        """Selected types that the employee may request: no allocation needed, or has remaining."""
        if not employee or not employee.company_id:
            return self.env["hr.leave.type"].browse()

        companies = employee.company_id
        if employee.user_id:
            companies |= employee.user_id.company_ids

        selected = self.env["hr.leave.type"].browse()
        for company in companies:
            selected |= company._anabtawi_configured_leave_types()

        if not selected:
            return selected

        LeaveType = selected.with_company(employee.company_id).with_context(
            employee_id=employee.id,
            default_employee_id=employee.id,
            allowed_company_ids=[employee.company_id.id],
        )
        allocation_by_id = {}
        if hasattr(LeaveType, "get_allocation_data"):
            rows = LeaveType.get_allocation_data(employee).get(employee, [])
            allocation_by_id = {row[3]: row[1] for row in rows}

        allowed = self.env["hr.leave.type"].browse()
        for leave_type in selected:
            if "requires_allocation" in leave_type._fields and not leave_type.requires_allocation:
                allowed |= leave_type
                continue
            remaining = allocation_by_id.get(leave_type.id, {}).get("virtual_remaining_leaves") or 0.0
            if remaining > 0:
                allowed |= leave_type
        return allowed


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    employee_app_leave_type_ids = fields.One2many(
        related="company_id.employee_app_leave_type_ids",
        readonly=False,
    )
