from odoo import models


class PosConfig(models.Model):
    _inherit = "pos.config"

    def _get_forbidden_change_fields(self):
        forbidden = super()._get_forbidden_change_fields()
        # Prevent changing Apex credentials while a session is open
        forbidden.update({
            "apex_enabled", "apex_service_url", "apex_mid",
            "apex_tid", "apex_secure_key", "apex_currency_code",
        })
        return forbidden
