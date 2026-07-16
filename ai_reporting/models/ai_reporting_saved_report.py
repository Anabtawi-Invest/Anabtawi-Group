import hashlib
import json

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

from odoo.addons.ai_reporting.services.optional_ai_tool import aitool

# Fields that action_run() (and similar bookkeeping) updates on behalf of any
# user who is merely allowed to *run* a shared report. These are excluded from
# the edit-permission check below so a "View and Run" share does not need
# "Edit Report Definition" just to record that it ran.
_EXECUTION_BOOKKEEPING_FIELDS = {
    "last_refresh_date",
    "last_execution_status",
    "last_execution_time",
    "last_record_count",
}


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

    def write(self, vals):
        if set(vals.keys()) - _EXECUTION_BOOKKEEPING_FIELDS:
            self._check_edit_permission()
        return super().write(vals)

    def unlink(self):
        self._check_edit_permission(manage=True)
        return super().unlink()

    def _check_edit_permission(self, manage=False):
        """Sharing a report only grants the permission level recorded on the
        share (run/export/parameters/edit/manage). ir.model.access.csv grants
        write/create at the model level for group_ai_reporting_user so that
        owners can manage their own reports; this method closes the gap that
        would otherwise let any user who can merely *see* a shared or
        company-visible report also edit or delete it."""
        if self.env.user.has_group("ai_reporting.group_ai_reporting_manager"):
            return
        allowed_permissions = ("manage",) if manage else ("edit", "manage")
        for report in self:
            if report.owner_id.id == self.env.user.id:
                continue
            share = self.env["ai.reporting.saved.report.share"].search([
                ("report_id", "=", report.id),
                ("user_id", "=", self.env.user.id),
                ("permission", "in", allowed_permissions),
            ], limit=1)
            if not share:
                raise AccessError(_(
                    "You do not have permission to %(action)s this report. "
                    "Ask the owner to share it with Edit or Manage Sharing permission."
                ) % {"action": _("delete") if manage else _("modify")})

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
            "visualization_type": definition.get("visualization_type", "table"),
            "chart_type": definition.get("chart_type"),
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

    # -- Optional OCA ai_tool integration -----------------------------------
    # These two methods are plain, safe, ACL-respecting entry points. They are
    # useful on their own even without ai_tool installed; when ai_tool *is*
    # installed, odoo_ai_bridge.register_integration() exposes them as
    # callable "tools" (see services/optional_ai_tool.py for how and why).

    @aitool(
        input_schema={},
        output_schema={"reports": {"type": "array"}},
    )
    def _ai_tool_list_reports(self):
        """List the active Advanced Reports the current user may run. Read
        access only -- runs with the caller's own permissions, no sudo."""
        reports = self.search([("state", "=", "active")])
        return {
            "reports": [
                {"id": report.id, "name": report.name, "description": report.description or ""}
                for report in reports
            ]
        }

    @aitool(
        input_schema={
            "report_id": {"type": "integer"},
            "parameters": {"type": "object"},
        },
        required_inputs=["report_id"],
        output_schema={"rows": {"type": "array"}, "record_count": {"type": "integer"}},
    )
    def _ai_tool_run_report(self, report_id, parameters=None):
        """Run one saved Advanced Report by id and return its rows, exactly
        like the Run button: current user, current data, no AI call, no
        sudo. Sharing/visibility rules apply normally through search()."""
        report = self.search([("id", "=", int(report_id))], limit=1)
        if not report:
            raise UserError(_("Report %s was not found or you do not have access to it.") % report_id)
        return report.action_run(parameters or {})

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
