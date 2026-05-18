# -*- coding: utf-8 -*-

from unittest.mock import MagicMock, patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.ai_assistant.services.ai_assistant_service import get_ai_assistant_service
from odoo.addons.ai_assistant.services.config import (
    PARAM_OPENAI_API_KEY,
    PARAM_PROVIDER,
    PROVIDER_MOCK,
    PROVIDER_OPENAI,
)
from odoo.addons.ai_assistant.services.mock_ai_service import MockAIService
from odoo.addons.ai_assistant.services.tool_executor import AIToolExecutor


@tagged("post_install", "-at_install")
class TestAiAssistant(TransactionCase):

    def test_factory_returns_mock_by_default(self):
        self.env["ir.config_parameter"].sudo().set_param(PARAM_PROVIDER, PROVIDER_MOCK)
        service = get_ai_assistant_service(self.env)
        self.assertIsInstance(service, MockAIService)

    def test_factory_returns_openai_when_configured(self):
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param(PARAM_PROVIDER, PROVIDER_OPENAI)
        icp.set_param(PARAM_OPENAI_API_KEY, "test-key")
        with patch.dict("sys.modules", {"openai": MagicMock()}):
            service = get_ai_assistant_service(self.env)
        self.assertEqual(service.__class__.__name__, "OpenAIService")

    def test_tool_executor_search_count(self):
        executor = AIToolExecutor(self.env)
        result = executor.execute(
            "search_count",
            {"model": "res.partner", "domain": []},
        )
        self.assertTrue(result.get("ok"))
        self.assertIsInstance(result.get("result"), int)

    def test_tool_executor_unknown_tool(self):
        executor = AIToolExecutor(self.env)
        result = executor.execute("unknown_tool", {})
        self.assertEqual(result.get("error"), "unknown_tool")

    def test_mock_chat_still_works(self):
        service = MockAIService(self.env)
        out = service.chat("How many invoices?")
        self.assertIn("content", out)
        self.assertEqual(out["meta"]["provider"], "mock")
