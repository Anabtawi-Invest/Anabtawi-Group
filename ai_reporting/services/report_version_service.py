from odoo import models


class AiReportingReportVersionService(models.AbstractModel):
    _name = "ai.reporting.report_version_service"
    _description = "AI Reporting Report Version Service"

    def create_draft_version(self, report):
        return report.action_create_draft_version()

    def activate_version(self, draft_report):
        draft_report.ensure_one()
        if draft_report.parent_version_id:
            draft_report.parent_version_id.state = "archived"
        draft_report.state = "active"
        return draft_report

