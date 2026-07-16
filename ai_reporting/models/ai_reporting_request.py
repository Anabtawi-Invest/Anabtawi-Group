import hashlib
import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from .ai_reporting_memory import normalize_text


class AiReportingRequest(models.Model):
    _name = "ai.reporting.request"
    _description = "AI Reporting Advanced Report Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(default=lambda self: _("New Advanced Report Request"), required=True)
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user, required=True, index=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, index=True)
    allowed_company_ids = fields.Many2many(
        "res.company",
        "ai_reporting_request_company_rel",
        "request_id",
        "company_id",
        string="Allowed Companies",
    )
    question = fields.Text(required=True)
    language_code = fields.Selection([("en", "English"), ("ar", "Arabic")], default="en")
    normalized_question = fields.Char(index=True)
    conversation_reference = fields.Char(index=True)
    draft_report_definition_json = fields.Json(default=dict)
    draft_parameter_schema_json = fields.Json(default=dict)
    validated_plan_json = fields.Json(default=dict)
    preview_result_metadata_json = fields.Json(default=dict)
    validation_result_json = fields.Json(default=dict)
    current_revision = fields.Integer(default=0)
    confirmed_revision = fields.Integer(default=0, readonly=True)
    confirmed_definition_hash = fields.Char(readonly=True)
    result_summary = fields.Text(readonly=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("generating", "Generating"),
            ("validation_failed", "Validation Failed"),
            ("preview_ready", "Preview Ready"),
            ("adjustment_requested", "Adjustment Requested"),
            ("regenerating", "Regenerating"),
            ("awaiting_confirmation", "Awaiting Confirmation"),
            ("confirmed", "Confirmed"),
            ("saved", "Saved"),
            ("cancelled", "Cancelled"),
            ("expired", "Expired"),
            ("failed", "Failed"),
        ],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    error_message = fields.Text(readonly=True)
    execution_time = fields.Float(readonly=True)
    record_count = fields.Integer(readonly=True)
    odoo_ai_request_id = fields.Char(readonly=True)
    model_name = fields.Char(readonly=True)
    token_usage = fields.Integer(readonly=True)
    estimated_cost = fields.Float(readonly=True)
    tokens_saved = fields.Integer(readonly=True)
    expiration_date = fields.Datetime()
    execution_date = fields.Datetime(readonly=True)
    saved_report_id = fields.Many2one("ai.reporting.saved.report", readonly=True, ondelete="set null")
    confirmed_by = fields.Many2one("res.users", readonly=True)
    confirmation_date = fields.Datetime(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("question") and not vals.get("normalized_question"):
                vals["normalized_question"] = normalize_text(vals["question"])
        return super().create(vals_list)

    def action_generate_draft(self):
        for request in self:
            request.state = "generating"
            plan = self.env["ai.reporting.odoo_ai_bridge"].create_report_draft(request.question)
            request._set_draft_plan(plan)
            request.action_preview()

    def action_preview(self):
        validator = self.env["ai.reporting.report_plan_validator"]
        executor = self.env["ai.reporting.report_execution_service"]
        for request in self:
            try:
                validation = validator.validate_plan(request.draft_report_definition_json, mode="report")
                preview = executor.preview_report(request.draft_report_definition_json)
            except Exception as exc:
                request.write({
                    "state": "validation_failed",
                    "error_message": str(exc),
                    "validation_result_json": {"valid": False, "error": str(exc)},
                })
                continue
            request.write({
                "validated_plan_json": request.draft_report_definition_json,
                "validation_result_json": validation,
                "preview_result_metadata_json": preview,
                "result_summary": preview.get("summary"),
                "record_count": preview.get("record_count", 0),
                "execution_date": fields.Datetime.now(),
                "state": "preview_ready",
            })

    def action_request_adjustment(self, adjustment):
        self.ensure_one()
        if not adjustment:
            raise UserError(_("Please provide the requested adjustment."))
        self.state = "adjustment_requested"
        plan = self.env["ai.reporting.odoo_ai_bridge"].adjust_report_draft(self.draft_report_definition_json, adjustment)
        self._set_draft_plan(plan)
        self.action_preview()

    def action_confirm(self, report_name=None):
        for request in self:
            if request.state not in ("preview_ready", "awaiting_confirmation"):
                raise UserError(_("Only a previewed report can be confirmed."))
            fingerprint = request._definition_hash(request.draft_report_definition_json)
            request.write({
                "state": "confirmed",
                "confirmed_by": self.env.user.id,
                "confirmation_date": fields.Datetime.now(),
                "confirmed_revision": request.current_revision,
                "confirmed_definition_hash": fingerprint,
                "name": report_name or request.name,
            })

    def action_save_report(self):
        report_model = self.env["ai.reporting.saved.report"]
        for request in self:
            if request.state != "confirmed":
                raise UserError(_("Confirm the exact report definition before saving."))
            if request.confirmed_definition_hash != request._definition_hash(request.draft_report_definition_json):
                request.state = "awaiting_confirmation"
                raise UserError(_("The report definition changed after confirmation. Please confirm again."))
            report = report_model.create_from_request(request)
            request.write({"state": "saved", "saved_report_id": report.id})
        return True

    def _set_draft_plan(self, plan):
        self.ensure_one()
        definition = plan.get("definition", plan)
        parameters = plan.get("parameters", definition.get("parameters", {}))
        self.write({
            "draft_report_definition_json": definition,
            "draft_parameter_schema_json": parameters,
            "current_revision": self.current_revision + 1,
            "confirmed_revision": 0,
            "confirmed_definition_hash": False,
            "state": "awaiting_confirmation",
        })

    @api.model
    def _definition_hash(self, definition):
        payload = json.dumps(definition or {}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

