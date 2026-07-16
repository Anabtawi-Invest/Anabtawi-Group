from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAiReporting(TransactionCase):

    def test_memory_exact_match_avoids_provider(self):
        plan = {"model": "res.partner", "domain": [], "fields": ["display_name"], "limit": 1}
        memory = self.env["ai.reporting.memory"].create({
            "name": "Partner count",
            "memory_type": "answer_query",
            "normalized_question": "partner count",
            "plan_json": plan,
            "state": "approved",
            "confidence_score": 1.0,
        })
        result = self.env["ai.reporting.memory_service"].resolve_question("partner count")
        self.assertEqual(result["resolution_type"], "exact_cache")
        self.assertEqual(result["memory"], memory)

    def test_parameterized_memory_reuses_query_with_fresh_parameters(self):
        self.env["res.partner"].create({"name": "Downtown Branch"})
        memory = self.env["ai.reporting.memory"].create({
            "name": "Sales for branch",
            "memory_type": "answer_query",
            "normalized_question": "sales for {branch}",
            "plan_json": {
                "model": "res.partner",
                "domain": [["name", "ilike", "$branch_name"]],
                "fields": ["display_name"],
                "limit": 5,
            },
            "parameter_schema_json": {
                "parameters": {
                    "branch": {
                        "type": "char",
                        "target": "branch_name",
                    }
                }
            },
            "state": "approved",
            "confidence_score": 1.0,
        })
        result = self.env["ai.reporting.memory_service"].answer_question("sales for Downtown Branch")
        self.assertEqual(memory.use_count, 1)
        self.assertEqual(result["model"], "res.partner")
        self.assertTrue(any(row["display_name"] == "Downtown Branch" for row in result["rows"]))

    def test_report_requires_confirmation_before_save(self):
        request = self.env["ai.reporting.request"].create({"question": "Create a partner report"})
        request._set_draft_plan({"definition": {"model": "res.partner", "fields": ["display_name"], "limit": 5}})
        with self.assertRaises(Exception):
            request.action_save_report()

    def test_saved_report_executes_without_ai(self):
        request = self.env["ai.reporting.request"].create({"question": "Create a partner report"})
        request._set_draft_plan({"definition": {"model": "res.partner", "fields": ["display_name"], "limit": 5}})
        request.action_preview()
        request.action_confirm("Partner Report")
        request.action_save_report()
        result = request.saved_report_id.action_run()
        self.assertIn("rows", result)

    def test_unsafe_sql_rejected(self):
        with self.assertRaises(Exception):
            self.env["ai.reporting.report_plan_validator"].validate_plan({
                "model": "res.partner",
                "domain": [["name", "=", "select * from res_users"]],
                "limit": 5,
            })

    def test_ai_bridge_detection_shape(self):
        status = self.env["ai.reporting.odoo_ai_bridge"].detect_native_ai()
        self.assertIn("native_available", status)
        self.assertIn("oca_available", status)
        self.assertIn("third_party", status)
        self.assertIn("models", status)

    def test_third_party_provider_requires_environment_key(self):
        self.env["ir.config_parameter"].set_param("ai_reporting.third_party_provider", "openai")
        self.env["ir.config_parameter"].set_param("ai_reporting.openai_api_key_env", "AI_REPORTING_TEST_KEY")
        with patch.dict("os.environ", {}, clear=True):
            status = self.env["ai.reporting.third_party_ai_provider"].get_status()
        self.assertEqual(status["provider"], "openai")
        self.assertFalse(status["configured"])
        self.assertIn("AI_REPORTING_TEST_KEY", status["missing"])
