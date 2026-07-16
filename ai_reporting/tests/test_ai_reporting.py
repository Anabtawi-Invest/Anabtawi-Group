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
        self.assertIn("models", status)
