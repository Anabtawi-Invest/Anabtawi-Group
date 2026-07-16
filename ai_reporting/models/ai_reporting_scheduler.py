from odoo import models


class AiReportingScheduler(models.Model):
    _name = "ai.reporting.scheduler"
    _description = "AI Reporting Scheduler"

    def _cron_refresh_metadata(self):
        return self.env["ai.reporting.discovery.service"].refresh_metadata(scan_addons=True, build_templates=False)
