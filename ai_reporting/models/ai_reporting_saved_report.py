import hashlib
import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AiReportingSavedReport(models.Model):
    _name = "ai.reporting.saved.report"
    _description = "AI Reporting Saved Report"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "write_date desc, id desc"

    name = fields.Char(required=True, tracking=True)
    description = fields.Text()
    owner_id = fields.Many2one("res.users", default=lambda self: self.env.user, required=True, index=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, index=True)
    allowed_company_ids = fields.Many2many(
        "res.company",
        "ai_reporting_saved_report_company_rel",
        "report_id",
        "company_id",
        string="Allowed Companies",
    )
    active = fields.Boolean(default=True)
    visibility = fields.Selection(
        [
            ("private", "Private"),
            ("company", "Company"),
            ("selected_users", "Selected Users"),
            ("selected_groups", "Selected Groups"),
            ("global", "Global"),
        ],
        default="private",
        required=True,
        index=True,
    )
    shared_user_ids = fields.Many2many(
        "res.users",
        "ai_reporting_saved_report_user_rel",
        "report_id",
        "user_id",
        string="Shared Users",
    )
    shared_group_ids = fields.Many2many(
        "res.groups",
        "ai_reporting_saved_report_group_rel",
        "report_id",
        "group_id",
        string="Shared Groups",
    )
    source_model_name = fields.Char(index=True)
    source_model_ids = fields.Many2many("ir.model", string="Source Models")
    report_type = fields.Selection(
        [("table", "Table"), ("pivot", "Pivot"), ("graph", "Graph"), ("list", "List"), ("kanban", "Kanban")],
        default="table",
        required=True,
    )
    report_definition_json = fields.Json(default=dict)
    domain_json = fields.Json(default=list)
    groupby_json = fields.Json(default=list)
    measures_json = fields.Json(default=list)
    calculated_measures_json = fields.Json(default=list)
    order_json = fields.Json(default=list)
    parameter_schema_json = fields.Json(default=dict)
    visualization_type = fields.Selection([("table", "Table"), ("chart", "Chart"), ("pivot", "Pivot")], default="table")
    chart_type = fields.Selection([("bar", "Bar"), ("line", "Line"), ("pie", "Pie")])
    date_field = fields.Char()
    limit = fields.Integer(default=500)
    state = fields.Selection([("draft", "Draft"), ("active", "Active"), ("archived", "Archived")], default="active", required=True)
    version = fields.Integer(default=1)
    parent_version_id = fields.Many2one("ai.reporting.saved.report", ondelete="set null")
    child_version_ids = fields.One2many("ai.reporting.saved.report", "parent_version_id")
    created_from_request_id = fields.Many2one("ai.reporting.request", ondelete="set null")
    created_from_memory_id = fields.Many2one("ai.reporting.memory", ondelete="set null")
    last_refresh_date = fields.Datetime(readonly=True)
    last_execution_status = fields.Char(readonly=True)
    last_execution_time = fields.Float(readonly=True)
    last_record_count = fields.Integer(readonly=True)
    schedule_id = fields.Many2one("ir.cron", ondelete="set null")
    dashboard_reference = fields.Char()
    confirmed_by = fields.Many2one("res.users", readonly=True)
    confirmation_date = fields.Datetime(readonly=True)
    confirmed_revision = fields.Integer(readonly=True)
    confirmed_definition_hash = fields.Char(readonly=True)
    share_ids = fields.One2many("ai.reporting.saved.report.share", "report_id", string="Sharing")

    @api.model
    def create_from_request(self, request):
        request.ensure_one()
        definition = request.draft_report_definition_json or {}
        fingerprint = self._definition_hash(definition)
        if fingerprint != request.confirmed_definition_hash:
            raise UserError(_("The confirmed definition no longer matches the draft."))
        model_names = definition.get("models") or [definition.get("model")]
        source_models = self.env["ir.model"].search([("model", "in", [name for name in model_names if name])])
        return self.create({
            "name": request.name,
            "description": definition.get("description"),
            "owner_id": request.user_id.id,
            "company_id": request.company_id.id,
            "source_model_name": definition.get("model"),
            "source_model_ids": [(6, 0, source_models.ids)],
            "report_type": definition.get("report_type", "table"),
            "report_definition_json": definition,
            "domain_json": definition.get("domain", []),
            "groupby_json": definition.get("groupby", []),
            "measures_json": definition.get("measures", []),
            "calculated_measures_json": definition.get("calculated_measures", []),
            "order_json": definition.get("order", []),
            "parameter_schema_json": request.draft_parameter_schema_json,
            "visualization_type": self._normalize_visualization_type(definition),
            "chart_type": self._normalize_chart_type(definition),
            "date_field": definition.get("date_field"),
            "limit": definition.get("limit", 500),
            "state": "active",
            "created_from_request_id": request.id,
            "confirmed_by": request.confirmed_by.id,
            "confirmation_date": request.confirmation_date,
            "confirmed_revision": request.confirmed_revision,
            "confirmed_definition_hash": request.confirmed_definition_hash,
        })

    def action_run(self, parameters=None):
        self.ensure_one()
        result = self.env["ai.reporting.report_execution_service"].execute_saved_report(self, parameters or {})
        self.write({
            "last_refresh_date": fields.Datetime.now(),
            "last_execution_status": "success",
            "last_execution_time": result.get("execution_time", 0.0),
            "last_record_count": result.get("record_count", 0),
        })
        return result

    def action_create_draft_version(self):
        self.ensure_one()
        values = self.copy_data()[0]
        values.update({
            "name": _("%s Draft") % self.name,
            "state": "draft",
            "version": self.version + 1,
            "parent_version_id": self.id,
            "confirmed_by": False,
            "confirmation_date": False,
            "confirmed_revision": 0,
            "confirmed_definition_hash": False,
        })
        return self.create(values)

    def action_archive(self):
        self.write({"state": "archived", "active": False})

    @api.model
    def _definition_hash(self, definition):
        payload = json.dumps(definition or {}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @api.model
    def _normalize_visualization_type(self, definition):
        visualization_type = (definition or {}).get("visualization_type") or "table"
        if visualization_type in ("bar", "line", "pie"):
            return "chart"
        if visualization_type in ("table", "chart", "pivot"):
            return visualization_type
        return "table"

    @api.model
    def _normalize_chart_type(self, definition):
        chart_type = (definition or {}).get("chart_type")
        visualization_type = (definition or {}).get("visualization_type")
        if chart_type in ("bar", "line", "pie"):
            return chart_type
        if visualization_type in ("bar", "line", "pie"):
            return visualization_type
        return False


class AiReportingSavedReportShare(models.Model):
    _name = "ai.reporting.saved.report.share"
    _description = "AI Reporting Saved Report Share"
    _order = "report_id, user_id"

    report_id = fields.Many2one("ai.reporting.saved.report", required=True, ondelete="cascade", index=True)
    user_id = fields.Many2one("res.users", required=True, index=True)
    permission = fields.Selection(
        [
            ("run", "View and Run"),
            ("export", "View, Run, and Export"),
            ("parameters", "Edit Parameters"),
            ("edit", "Edit Report Definition"),
            ("manage", "Manage Sharing"),
        ],
        required=True,
        default="run",
    )

    _sql_constraints = [
        ("unique_report_user", "unique(report_id, user_id)", "A user can only be shared once per report."),
    ]
