from odoo import models

from odoo.addons.ai_reporting.models.ai_reporting_memory import normalize_text, stable_hash


class AiReportingMemoryService(models.AbstractModel):
    _name = "ai.reporting.memory_service"
    _description = "AI Reporting Local Memory Service"

    def resolve_question(self, question):
        normalized = normalize_text(question)
        question_hash = stable_hash(normalized)
        memory = self.env["ai.reporting.memory"].search([
            ("active", "=", True),
            ("state", "=", "approved"),
            ("memory_type", "=", "answer_query"),
            ("question_hash", "=", question_hash),
        ], limit=1)
        if memory:
            return {"resolution_type": "exact_cache", "memory": memory}
        phrase = self.env["ai.reporting.memory.phrase"].search([
            ("active", "=", True),
            ("phrase_hash", "=", question_hash),
            ("memory_id.state", "=", "approved"),
        ], limit=1)
        if phrase:
            return {"resolution_type": "semantic_cache", "memory": phrase.memory_id, "similarity_score": 1.0}
        return {"resolution_type": "external_provider", "memory": self.env["ai.reporting.memory"]}

    def answer_question(self, question, parameters=None):
        resolved = self.resolve_question(question)
        memory = resolved.get("memory")
        if memory:
            result = self.env["ai.reporting.query_execution_service"].execute_plan(memory.plan_json, parameters or {})
            memory.record_execution(
                question,
                resolution_type=resolved.get("resolution_type"),
                tokens_saved=memory.original_token_usage or 0,
                similarity_score=resolved.get("similarity_score", 0.0),
            )
            return result
        return self.env["ai.reporting.odoo_ai_bridge"].ask_native_provider(question, parameters or {})

    def create_memory_candidate(self, question, plan, provider_name=None, token_usage=0):
        return self.env["ai.reporting.memory"].create({
            "name": question[:120],
            "memory_type": "answer_query",
            "normalized_question": normalize_text(question),
            "plan_json": plan,
            "provider_name": provider_name,
            "original_token_usage": token_usage,
            "state": "validated",
            "confidence_score": 0.7,
        })

