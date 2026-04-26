from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    required_weekly_hours = fields.Float(
        string="Required Weekly Hours",
        config_parameter="hr_attendance_weekly_overtime_eligibility.required_weekly_hours",
        help="Minimum weekly worked hours an employee must complete before overtime can be approved.",
    )
