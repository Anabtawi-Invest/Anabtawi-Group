# -*- coding: utf-8 -*-
from odoo import fields, models

from .meps_client import DEFAULT_MEPS_TIMEOUT, DEFAULT_MEPS_URL
from odoo.addons.pos_meps_terminal.meps_mock_payload import ICP_ENABLE_MOCK


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    meps_endpoint_url = fields.Char(
        string="MEPS Gateway URL",
        config_parameter="pos_mep_id.endpoint_url",
        default=DEFAULT_MEPS_URL,
        help="SOAP endpoint for the MEPS/ApexECR web service. Use the built-in mock URL "
        "on Odoo.sh when you have no real terminal.",
    )
    meps_timeout = fields.Integer(
        string="MEPS Request Timeout (seconds)",
        config_parameter="pos_mep_id.timeout",
        default=DEFAULT_MEPS_TIMEOUT,
        help="How long to wait for the physical terminal (or mock) to respond before giving up.",
    )
    meps_enable_mock = fields.Boolean(
        string="Enable built-in MEPS mock gateway",
        config_parameter=ICP_ENABLE_MOCK,
        help="Exposes /pos_meps_terminal/mock on this database so you can test Sale/Void/"
        "Settlement without a physical terminal or tunnel. Disable before go-live.",
    )

    def action_meps_use_mock_url(self):
        """Fill Gateway URL with this database's built-in mock endpoint (success scenario)."""
        self.ensure_one()
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url").rstrip("/")
        mock_url = f"{base}/pos_meps_terminal/mock"
        self.env["ir.config_parameter"].sudo().set_param("pos_mep_id.endpoint_url", mock_url)
        self.env["ir.config_parameter"].sudo().set_param(ICP_ENABLE_MOCK, "True")
        self.meps_endpoint_url = mock_url
        self.meps_enable_mock = True
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "MEPS mock ready",
                "message": f"Gateway URL set to {mock_url}. Create a MEPS payment method and pay in POS.",
                "type": "success",
                "sticky": False,
            },
        }

    def action_meps_use_mock_decline_url(self):
        """Same as success mock, but responses are declines."""
        self.ensure_one()
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url").rstrip("/")
        mock_url = f"{base}/pos_meps_terminal/mock?scenario=decline"
        self.env["ir.config_parameter"].sudo().set_param("pos_mep_id.endpoint_url", mock_url)
        self.env["ir.config_parameter"].sudo().set_param(ICP_ENABLE_MOCK, "True")
        self.meps_endpoint_url = mock_url
        self.meps_enable_mock = True
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "MEPS mock (decline)",
                "message": f"Gateway URL set to {mock_url}",
                "type": "warning",
                "sticky": False,
            },
        }
