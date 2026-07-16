from odoo import fields, models


class AiReportingDiscoveryWizard(models.TransientModel):
    _name = "ai.reporting.discovery.wizard"
    _description = "AI Reporting Discovery Wizard"

    scan_addons = fields.Boolean(default=True)
    build_query_templates = fields.Boolean(default=True)
    result_json = fields.Json(readonly=True)

    def action_run_discovery(self):
        self.ensure_one()
        result = self.env["ai.reporting.discovery.service"].refresh_metadata(
            scan_addons=self.scan_addons,
            build_templates=self.build_query_templates,
        )
        self.result_json = result
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
