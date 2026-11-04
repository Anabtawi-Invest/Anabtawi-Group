from odoo import fields, models


class AnabtawiEmployeeAppLeaveType(models.Model):
    _name = "anabtawi.employee.app.leave.type"
    _description = "Time off type shown in the Employee App"
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
        "hr.work.entry.type",
        string="Time Off Type",
        required=True,
        ondelete="cascade",
    )

    _company_leave_type_unique = models.Constraint(
        "UNIQUE(company_id, leave_type_id)",
        "This time off type is already selected for the Employee App.",
    )


class ResCompany(models.Model):
    _inherit = "res.company"

    employee_app_leave_type_ids = fields.One2many(
        "anabtawi.employee.app.leave.type",
        "company_id",
        string="Employee App Time Off Types",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    employee_app_leave_type_ids = fields.One2many(
        related="company_id.employee_app_leave_type_ids",
        readonly=False,
    )
