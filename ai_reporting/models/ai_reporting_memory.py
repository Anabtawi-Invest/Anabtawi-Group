import hashlib
import json
import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


def _json_dumps(value):
    return json.dumps(value or {}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def normalize_text(text):
    value = (text or "").strip().lower()
    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ة": "ه",
        "ؤ": "و",
        "ئ": "ي",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    value = re.sub(r"[\u064b-\u065f\u0670]", "", value)
    value = re.sub(r"\s+", " ", value)
    return value


def stable_hash(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


class AiReportingMemory(models.Model):
    _name = "ai.reporting.memory"
    _description = "AI Reporting Local Memory"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "last_used_at desc, id desc"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    memory_type = fields.Selection(
        [
            ("answer_query", "Ask AI Answer Query"),
            ("report_template", "Advanced Report Template"),
            ("advanced_report", "Confirmed Advanced Report"),
        ],
        required=True,
        default="answer_query",
        index=True,
        tracking=True,
    )
    owner_id = fields.Many2one("res.users", default=lambda self: self.env.user, required=True, index=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, index=True)
    allowed_company_ids = fields.Many2many(
        "res.company",
        "ai_reporting_memory_company_rel",
        "memory_id",
        "company_id",
        string="Allowed Companies",
    )
    visibility = fields.Selection(
        [
            ("private", "Private"),
            ("company", "Company"),
            ("selected_users", "Selected Users"),
            ("selected_groups", "Selected Groups"),
            ("global", "Global"),
        ],
        required=True,
        default="private",
        index=True,
    )
    shared_user_ids = fields.Many2many(
        "res.users",
        "ai_reporting_memory_user_rel",
        "memory_id",
        "user_id",
        string="Shared Users",
    )
    shared_group_ids = fields.Many2many(
        "res.groups",
        "ai_reporting_memory_group_rel",
        "memory_id",
        "group_id",
        string="Shared Groups",
    )
    intent_code = fields.Char(index=True)
    source_model_name = fields.Char(index=True)
    normalized_question = fields.Char(index=True)
    question_hash = fields.Char(index=True, copy=False)
    plan_json = fields.Json(default=dict)
    parameter_schema_json = fields.Json(default=dict)
    plan_fingerprint = fields.Char(index=True, copy=False)
    language_code = fields.Selection([("en", "English"), ("ar", "Arabic")], default="en", index=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("validated", "Validated"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("expired", "Expired"),
            ("disabled", "Disabled"),
        ],
        required=True,
        default="draft",
        index=True,
        tracking=True,
    )
    confidence_score = fields.Float(default=0.0)
    use_count = fields.Integer(default=0, readonly=True)
    successful_use_count = fields.Integer(default=0, readonly=True)
    failure_count = fields.Integer(default=0, readonly=True)
    last_used_at = fields.Datetime(readonly=True)
    expires_at = fields.Datetime()
    metadata_version = fields.Char(default="1")
    schema_version = fields.Char(default="1.0")
    provider_request_id = fields.Char(readonly=True)
    provider_name = fields.Char(readonly=True)
    original_token_usage = fields.Integer(readonly=True)
    estimated_tokens_saved = fields.Integer(default=0, readonly=True)
    phrase_ids = fields.One2many("ai.reporting.memory.phrase", "memory_id", string="Phrases")
    execution_ids = fields.One2many("ai.reporting.memory.execution", "memory_id", string="Executions")
    feedback_ids = fields.One2many("ai.reporting.memory.feedback", "memory_id", string="Feedback")

    _sql_constraints = [
        ("question_hash_unique", "unique(question_hash, company_id, memory_type)", "This memory question already exists for the company."),
        ("plan_fingerprint_unique", "unique(plan_fingerprint, company_id, memory_type)", "This memory plan already exists for the company."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._prepare_hash_values(vals)
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        self._prepare_hash_values(vals)
        return super().write(vals)

    @api.model
    def _prepare_hash_values(self, vals):
        question = vals.get("normalized_question") or vals.get("name")
        if question and not vals.get("normalized_question"):
            vals["normalized_question"] = normalize_text(question)
        if vals.get("normalized_question"):
            vals["question_hash"] = stable_hash(vals["normalized_question"])
        if "plan_json" in vals:
            vals["plan_fingerprint"] = stable_hash(_json_dumps(vals.get("plan_json")))

    def action_validate(self):
        validator = self.env["ai.reporting.report_plan_validator"]
        for memory in self:
            validator.validate_plan(memory.plan_json, mode="query")
            memory.state = "validated"

    def action_approve(self):
        self.write({"state": "approved", "confidence_score": 1.0})

    def action_disable(self):
        self.write({"state": "disabled", "active": False})

    def record_execution(self, question, status="success", provider_called=False, tokens_saved=0, **extra):
        self.ensure_one()
        vals = {
            "user_id": self.env.user.id,
            "company_id": self.env.company.id,
            "question": question,
            "normalized_question": normalize_text(question),
            "memory_id": self.id,
            "resolution_type": extra.get("resolution_type", "exact_cache"),
            "provider_called": provider_called,
            "tokens_saved": tokens_saved,
            "status": status,
            "error_message": extra.get("error_message"),
            "similarity_score": extra.get("similarity_score", 0.0),
            "confidence_score": self.confidence_score,
            "execution_time_ms": extra.get("execution_time_ms", 0),
        }
        execution = self.env["ai.reporting.memory.execution"].create(vals)
        update = {
            "use_count": self.use_count + 1,
            "last_used_at": fields.Datetime.now(),
            "estimated_tokens_saved": self.estimated_tokens_saved + tokens_saved,
        }
        if status == "success":
            update["successful_use_count"] = self.successful_use_count + 1
        else:
            update["failure_count"] = self.failure_count + 1
        self.write(update)
        return execution


class AiReportingMemoryPhrase(models.Model):
    _name = "ai.reporting.memory.phrase"
    _description = "AI Reporting Memory Phrase"
    _order = "memory_id, id"

    memory_id = fields.Many2one("ai.reporting.memory", required=True, ondelete="cascade", index=True)
    phrase = fields.Char(required=True)
    normalized_phrase = fields.Char(index=True)
    search_normalized_phrase = fields.Char(index=True)
    phrase_hash = fields.Char(index=True, copy=False)
    language_code = fields.Selection([("en", "English"), ("ar", "Arabic")], default="en", index=True)
    variant_type = fields.Selection(
        [
            ("canonical", "Canonical"),
            ("paraphrase", "Paraphrase"),
            ("translation", "Translation"),
            ("alias", "Alias"),
        ],
        default="canonical",
        required=True,
    )
    arabic_variant = fields.Selection(
        [
            ("msa", "Modern Standard Arabic"),
            ("egyptian", "Egyptian"),
            ("gulf", "Gulf"),
        ]
    )
    source_phrase_id = fields.Many2one("ai.reporting.memory.phrase", ondelete="set null")
    translation_status = fields.Selection(
        [("pending", "Pending"), ("generated", "Generated"), ("approved", "Approved"), ("rejected", "Rejected")],
        default="pending",
    )
    embedding_reference = fields.Char()
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("phrase_hash_unique", "unique(phrase_hash, memory_id)", "This phrase already exists for the memory."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._prepare_phrase(vals)
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        self._prepare_phrase(vals)
        return super().write(vals)

    @api.model
    def _prepare_phrase(self, vals):
        if vals.get("phrase"):
            normalized = normalize_text(vals["phrase"])
            vals.setdefault("normalized_phrase", normalized)
            vals.setdefault("search_normalized_phrase", normalized)
            vals["phrase_hash"] = stable_hash(normalized)


class AiReportingMemoryExecution(models.Model):
    _name = "ai.reporting.memory.execution"
    _description = "AI Reporting Memory Execution"
    _order = "create_date desc, id desc"

    user_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, index=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, index=True)
    question = fields.Text()
    normalized_question = fields.Char(index=True)
    memory_id = fields.Many2one("ai.reporting.memory", ondelete="set null", index=True)
    saved_report_id = fields.Many2one("ai.reporting.saved.report", ondelete="set null", index=True)
    resolution_type = fields.Selection(
        [
            ("exact_cache", "Exact Cache"),
            ("parameterized_intent", "Parameterized Intent"),
            ("semantic_cache", "Semantic Cache"),
            ("saved_report", "Saved Report"),
            ("report_template", "Report Template"),
            ("local_model", "Local Model"),
            ("external_provider", "External Provider"),
        ],
        required=True,
        default="external_provider",
        index=True,
    )
    similarity_score = fields.Float(default=0.0)
    confidence_score = fields.Float(default=0.0)
    provider_called = fields.Boolean(default=False)
    input_tokens = fields.Integer(default=0)
    output_tokens = fields.Integer(default=0)
    tokens_saved = fields.Integer(default=0)
    execution_time_ms = fields.Integer(default=0)
    status = fields.Selection([("success", "Success"), ("failed", "Failed"), ("blocked", "Blocked")], default="success", index=True)
    error_message = fields.Text()


class AiReportingMemoryFeedback(models.Model):
    _name = "ai.reporting.memory.feedback"
    _description = "AI Reporting Memory Feedback"
    _order = "create_date desc, id desc"

    memory_id = fields.Many2one("ai.reporting.memory", required=True, ondelete="cascade", index=True)
    execution_id = fields.Many2one("ai.reporting.memory.execution", ondelete="set null", index=True)
    user_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user)
    rating = fields.Integer()
    feedback_type = fields.Selection(
        [
            ("correct", "Correct"),
            ("partially_correct", "Partially Correct"),
            ("incorrect", "Incorrect"),
            ("outdated", "Outdated"),
            ("unsafe", "Unsafe"),
            ("wrong_scope", "Wrong Scope"),
            ("wrong_translation", "Wrong Translation"),
            ("wrong_intent", "Wrong Intent"),
        ],
        required=True,
    )
    comment = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        negative = {"incorrect", "outdated", "unsafe", "wrong_scope", "wrong_translation", "wrong_intent"}
        for feedback in records.filtered(lambda item: item.feedback_type in negative):
            memory = feedback.memory_id
            memory.confidence_score = max(0.0, memory.confidence_score - 0.2)
            if memory.confidence_score < 0.3:
                memory.state = "disabled"
        return records

