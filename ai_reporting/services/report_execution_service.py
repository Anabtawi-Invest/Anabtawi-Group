from odoo import _, models
from odoo.exceptions import ValidationError


class AiReportingReportExecutionService(models.AbstractModel):
    _name = "ai.reporting.report_execution_service"
    _description = "AI Reporting Report Execution Service"

    def preview_report(self, definition, parameters=None):
        plan = dict(definition or {})
        plan["limit"] = min(int(plan.get("limit") or 20), 20)
        result = self.env["ai.reporting.query_execution_service"].execute_plan(plan, parameters or {}, preview=True)
        return {
            "summary": _("Preview generated from the exact draft definition."),
            "record_count": result.get("record_count", 0),
            "sample_rows": result.get("rows", [])[:20],
            "grouped": result.get("grouped", False),
            "execution_time": result.get("execution_time", 0.0),
            "warnings": self._warnings(plan),
        }

    def execute_saved_report(self, report, parameters=None):
        report.ensure_one()
        definition = dict(report.report_definition_json or {})
        if not definition:
            raise ValidationError(_("The saved report has no definition."))
        return self.env["ai.reporting.query_execution_service"].execute_plan(definition, parameters or {}, preview=False)

    def _warnings(self, plan):
        warnings = []
        if not plan.get("date_field"):
            warnings.append(_("No date basis was defined."))
        if not plan.get("groupby"):
            warnings.append(_("The preview is not grouped."))
        return warnings

