from odoo import fields, models


class PosCloseAllowedDevice(models.Model):
    _name = "pos.close.allowed.device"
    _description = "POS device allowed to close the session"
    _order = "name, id"

    config_id = fields.Many2one(
        "pos.config",
        string="Point of Sale",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(string="Device Name", required=True)
    device_token = fields.Char(string="Device Token", required=True, index=True, copy=False)

    _device_token_unique = models.Constraint(
        "unique(config_id, device_token)",
        "This device is already allowed to close this Point of Sale.",
    )
