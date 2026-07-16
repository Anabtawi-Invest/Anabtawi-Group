from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAiReporting(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_ai_user = cls.env.ref("ai_reporting.group_ai_reporting_user")
        cls.owner = cls.env["res.users"].create({
            "name": "AI Reporting Owner",
            "login": "ai_reporting_owner",
            "email": "ai_reporting_owner@example.com",
            "group_ids": [(4, cls.group_ai_user.id)],
        })
        cls.viewer = cls.env["res.users"].create({
            "name": "AI Reporting Viewer",
            "login": "ai_reporting_viewer",
            "email": "ai_reporting_viewer@example.com",
            "group_ids": [(4, cls.group_ai_user.id)],
        })

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

    def test_view_only_share_cannot_edit_or_delete_report(self):
        report = self.env["ai.reporting.saved.report"].with_user(self.owner).create({
            "name": "Owner Report",
            "owner_id": self.owner.id,
            "visibility": "selected_users",
            "shared_user_ids": [(4, self.viewer.id)],
            "report_definition_json": {"model": "res.partner", "fields": ["display_name"], "limit": 5},
        })
        self.env["ai.reporting.saved.report.share"].with_user(self.owner).create({
            "report_id": report.id,
            "user_id": self.viewer.id,
            "permission": "run",
        })
        visible = self.env["ai.reporting.saved.report"].with_user(self.viewer).search([("id", "=", report.id)])
        self.assertTrue(visible, "The viewer should be able to see the shared report.")
        report_as_viewer = report.with_user(self.viewer)
        with self.assertRaises(AccessError):
            report_as_viewer.write({"name": "Renamed by viewer"})
        with self.assertRaises(AccessError):
            report_as_viewer.unlink()
        # Bookkeeping fields written by action_run() must stay usable for a run-only share.
        report_as_viewer.write({"last_execution_status": "success"})
        self.assertEqual(report_as_viewer.last_execution_status, "success")

    def test_edit_share_permission_allows_write(self):
        report = self.env["ai.reporting.saved.report"].with_user(self.owner).create({
            "name": "Owner Report Editable",
            "owner_id": self.owner.id,
            "visibility": "selected_users",
            "shared_user_ids": [(4, self.viewer.id)],
            "report_definition_json": {"model": "res.partner", "fields": ["display_name"], "limit": 5},
        })
        self.env["ai.reporting.saved.report.share"].with_user(self.owner).create({
            "report_id": report.id,
            "user_id": self.viewer.id,
            "permission": "edit",
        })
        report.with_user(self.viewer).write({"description": "Edited by viewer with edit permission"})
        self.assertEqual(report.description, "Edited by viewer with edit permission")

    def test_date_range_limit_is_enforced(self):
        self.env["ir.config_parameter"].set_param("ai_reporting.maximum_date_range", 30)
        plan = {
            "model": "res.partner",
            "domain": [["create_date", ">=", "2020-01-01"], ["create_date", "<=", "2020-12-31"]],
            "fields": ["display_name"],
            "limit": 5,
        }
        with self.assertRaises(ValidationError):
            self.env["ai.reporting.query_execution_service"].execute_plan(plan)

    def test_native_ai_registration_is_a_safe_no_op_without_the_real_app(self):
        # This sandbox has no Enterprise "ai" app installed, so ir.actions.server
        # has none of use_in_ai/ai_tool_description/ai_tool_schema. Confirms the
        # bridge detects that correctly and never raises trying to register tools
        # against a schema that isn't there.
        bridge = self.env["ai.reporting.odoo_ai_bridge"]
        self.assertFalse(bridge._native_ai_app_ready())
        status = bridge.register_integration()
        self.assertFalse(status["native_available"])
        self.assertEqual(status["native_tools_registered"], 0)

    def test_native_ai_tool_methods_are_directly_callable(self):
        # The methods the native-AI "code" tools call (model.env[...]._ai_tool_*)
        # must work as plain Python regardless of whether the ai app is installed.
        report = self.env["ai.reporting.saved.report"].with_user(self.owner).create({
            "name": "Callable Tool Report",
            "owner_id": self.owner.id,
            "report_definition_json": {"model": "res.partner", "fields": ["display_name"], "limit": 5},
        })
        listing = report.with_user(self.owner)._ai_tool_list_reports()
        self.assertIn(report.id, [row["id"] for row in listing["reports"]])
        result = self.env["ai.reporting.saved.report"].with_user(self.owner)._ai_tool_run_report(report.id)
        self.assertIn("rows", result)
        draft = self.env["ai.reporting.request"].with_user(self.owner)._ai_tool_create_advanced_report(
            "Create a partner report"
        )
        self.assertIn("request_id", draft)
        self.assertIn("state", draft)

    def test_format_local_memory_chat_reply_renders_markdown_table(self):
        bridge = self.env["ai.reporting.odoo_ai_bridge"]
        result = {
            "rows": [
                {"id": 1, "display_name": "Downtown Branch"},
                {"id": 2, "display_name": "Uptown Branch"},
            ],
            "record_count": 2,
        }
        message = bridge.format_local_memory_chat_reply("sales for Downtown Branch", result)
        self.assertIn("Local Memory", message)
        self.assertIn("Downtown Branch", message)
        self.assertIn("Uptown Branch", message)
        self.assertNotIn("| id |", message, "The internal id column should not be shown in the chat reply.")

    def test_format_local_memory_chat_reply_handles_empty_rows(self):
        bridge = self.env["ai.reporting.odoo_ai_bridge"]
        message = bridge.format_local_memory_chat_reply("sales for Nowhere", {"rows": [], "record_count": 0})
        self.assertIn("0 result", message)

    def test_multi_company_isolation_hides_other_company_reports(self):
        other_company = self.env["res.company"].create({"name": "AI Reporting Other Co"})
        report = self.env["ai.reporting.saved.report"].create({
            "name": "Other Company Report",
            "owner_id": self.owner.id,
            "company_id": other_company.id,
            "visibility": "global",
            "report_definition_json": {"model": "res.partner", "fields": ["display_name"], "limit": 5},
        })
        visible = self.env["ai.reporting.saved.report"].with_user(self.viewer).search([("id", "=", report.id)])
        self.assertFalse(visible, "A report scoped to a company the user has no access to must stay hidden.")
