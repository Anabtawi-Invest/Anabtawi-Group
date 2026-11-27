# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    talabat_sync_enabled = fields.Boolean(
        string="Enable daily Talabat review sync",
        config_parameter="talabat_reviews.sync_enabled",
    )
    talabat_session_cookie = fields.Char(
        string="Talabat session cookie",
        help="From a logged-in browser: DevTools → Network → any partner-app request → Request Headers → Cookie.",
        config_parameter="talabat_reviews.session_cookie",
    )
    talabat_login_email = fields.Char(
        string="Talabat login email",
        config_parameter="talabat_reviews.login_email",
    )
    talabat_sync_status = fields.Char(
        string="Last sync status",
        readonly=True,
        config_parameter="talabat_reviews.sync_status",
    )
    talabat_sync_message = fields.Char(
        string="Last sync message",
        readonly=True,
        config_parameter="talabat_reviews.sync_message",
    )
    talabat_last_sync_at = fields.Char(
        string="Last sync at",
        readonly=True,
        config_parameter="talabat_reviews.last_sync_at",
    )

    def action_talabat_sync_now(self):
        self.env["talabat.sync.mixin"].sync_reviews(fetch_order_lines=True)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Talabat Reviews",
                "message": self.env["ir.config_parameter"].sudo().get_param(
                    "talabat_reviews.sync_message", "Sync finished."
                ),
                "sticky": False,
                "type": "success",
            },
        }
