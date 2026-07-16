from odoo import fields, models


class AiReportingDiscoveryService(models.AbstractModel):
    _name = "ai.reporting.discovery.service"
    _description = "AI Reporting Discovery Service"

    def refresh_metadata(self):
        models_count = self.env["ir.model"].search_count([])
        fields_count = self.env["ir.model.fields"].search_count([])
        self.env["ir.config_parameter"].set_param("ai_reporting.last_discovery_at", fields.Datetime.now())
        self.env["ir.config_parameter"].set_param("ai_reporting.discovery_model_count", models_count)
        self.env["ir.config_parameter"].set_param("ai_reporting.discovery_field_count", fields_count)
        self.env["ai.reporting.odoo_ai_bridge"].register_integration()
        return {"models": models_count, "fields": fields_count}

