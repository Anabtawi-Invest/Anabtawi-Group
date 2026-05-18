from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    planning_max_extra_hours = fields.Float(
        string="Maximum Extra Hours for Shift Assignment",
        compute="_compute_planning_max_extra_hours",
        inverse="_inverse_planning_max_extra_hours",
        readonly=False,
        help="Maximum allowed extra hours before blocking new shift assignment. Set to 0 to disable the limit.",
    )

    def _compute_planning_max_extra_hours(self):
        params = self.env["ir.config_parameter"].sudo()
        for company in self:
            company_key = f"planning_enhancement.max_extra_hours.company_{company.id}"
            value = params.get_param(company_key)
            if value is None:
                # Backward compatibility with the previously used global key.
                value = params.get_param("planning_enhancement.max_extra_hours", default=0.0)
            company.planning_max_extra_hours = float(value or 0.0)

    def _inverse_planning_max_extra_hours(self):
        params = self.env["ir.config_parameter"].sudo()
        for company in self:
            company_key = f"planning_enhancement.max_extra_hours.company_{company.id}"
            params.set_param(company_key, company.planning_max_extra_hours or 0.0)
