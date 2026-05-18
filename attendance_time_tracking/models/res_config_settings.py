from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    enforce_checkin_window = fields.Boolean(
        string='Enforce Check-in Window',
        config_parameter='attendance_time_tracking.enforce_checkin_window',
        default=True,
        help='When enabled, employees can only check in during their scheduled work hours.',
    )
    checkin_tolerance_minutes = fields.Integer(
        string='Early Check-in Tolerance (minutes)',
        config_parameter='attendance_time_tracking.checkin_tolerance_minutes',
        default=30,
        help='How many minutes before the scheduled shift start an employee is allowed to check in.',
    )
    auto_checkout_enabled = fields.Boolean(
        string='Enable Auto Check-out',
        config_parameter='attendance_time_tracking.auto_checkout_enabled',
        default=True,
        help='Automatically check out employees who forgot to check out.',
    )
    auto_checkout_grace_minutes = fields.Integer(
        string='Auto Check-out Grace Period (minutes)',
        config_parameter='attendance_time_tracking.auto_checkout_grace_minutes',
        default=15,
        help='Minutes after scheduled shift end before auto check-out is triggered.',
    )

    @api.model
    def _get_att_config(self):
        """Return a dict of all attendance tracking config values."""
        ICP = self.env['ir.config_parameter'].sudo()
        return {
            'enforce_checkin_window': ICP.get_param(
                'attendance_time_tracking.enforce_checkin_window', 'True') == 'True',
            'checkin_tolerance_minutes': int(ICP.get_param(
                'attendance_time_tracking.checkin_tolerance_minutes', 30)),
            'auto_checkout_enabled': ICP.get_param(
                'attendance_time_tracking.auto_checkout_enabled', 'True') == 'True',
            'auto_checkout_grace_minutes': int(ICP.get_param(
                'attendance_time_tracking.auto_checkout_grace_minutes', 15)),
        }
