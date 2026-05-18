# -*- coding: utf-8 -*-

import re

from odoo import _

from .ai_tools import OdooAITools
from .config import is_ai_assistant_enabled
from .exceptions import AiAssistantError


class MockAIService:
    """Mock AI backend that routes simple intents to generic ORM tools."""

    def __init__(self, env):
        self.env = env
        self.tools = OdooAITools(env)

    def is_enabled(self):
        return is_ai_assistant_enabled(self.env)

    def chat(self, user_message, history=None):
        """Process a user message and return a mock assistant reply."""
        del history  # stateless mock; history reserved for future providers

        if not self.is_enabled():
            raise AiAssistantError(_("AI Assistant is disabled."), "disabled")

        user_message = (user_message or "").strip()
        if not user_message:
            raise AiAssistantError(_("Message cannot be empty."), "empty_message")

        intent = self._detect_intent(user_message)
        handler = getattr(self, f"_handle_{intent}", self._handle_generic)
        content, meta = handler(user_message)
        return {"content": content, "meta": meta}

    def _detect_intent(self, message):
        text = message.lower()
        if re.search(r"\b(invoice|invoices|billing|bill)\b", text):
            return "invoices"
        if re.search(r"\b(customer|customers|client|clients|partner|partners|contact|contacts)\b", text):
            return "customers"
        if re.search(
            r"\b(top\s+selling|best\s+selling|best\s+seller|top\s+product|top\s+products|selling\s+product)\b",
            text,
        ):
            return "top_products"
        return "generic"

    def _handle_invoices(self, message):
        del message
        if "account.move" not in self.env:
            return self._reply(
                "invoices",
                _("The Accounting app is not installed, so I cannot count invoices."),
                tool_calls=[],
            )

        domain = [("move_type", "in", ("out_invoice", "in_invoice", "out_refund", "in_refund"))]
        count = self.tools.search_count("account.move", domain)
        content = _("You have %(count)s invoice(s) in the system.", count=count)
        return self._reply(
            "invoices",
            content,
            tool_calls=[
                {
                    "tool": "search_count",
                    "model": "account.move",
                    "domain": domain,
                    "result": count,
                }
            ],
        )

    def _customer_domain(self):
        partner_model = self.env["res.partner"]
        if "customer_rank" in partner_model._fields:
            return [("customer_rank", ">", 0)]
        return [("is_company", "=", True)]

    def _handle_customers(self, message):
        del message
        domain = self._customer_domain()
        records = self.tools.search_records(
            "res.partner",
            domain=domain,
            fields=["display_name", "email", "phone"],
            limit=10,
        )
        count = self.tools.search_count("res.partner", domain)
        if not records:
            content = _("You have no customers matching the default filter.")
        else:
            names = ", ".join(r.get("display_name") or _("Unnamed") for r in records)
            content = _(
                "You have %(count)s customer(s). Here are up to 10: %(names)s",
                count=count,
                names=names,
            )
        return self._reply(
            "customers",
            content,
            tool_calls=[
                {
                    "tool": "search_count",
                    "model": "res.partner",
                    "domain": domain,
                    "result": count,
                },
                {
                    "tool": "search_records",
                    "model": "res.partner",
                    "domain": domain,
                    "limit": 10,
                    "result": records,
                },
            ],
        )

    def _handle_top_products(self, message):
        del message
        if "sale.order.line" not in self.env:
            return self._reply(
                "top_products",
                _("The Sales app is not installed, so I cannot aggregate product sales."),
                tool_calls=[],
            )

        groups = self.tools.aggregate_records(
            "sale.order.line",
            domain=[],
            fields=["product_id", "product_uom_qty:sum"],
            groupby=["product_id"],
            limit=10,
        )
        if not groups:
            content = _("No sales order lines found to compute top products.")
        else:
            lines = []
            for group in groups[:5]:
                product = group.get("product_id")
                qty = group.get("product_uom_qty") or 0
                name = product[1] if product else _("Unknown product")
                lines.append(f"- {name}: {qty:g}")
            content = _("Top selling products (by ordered quantity):\n%(lines)s", lines="\n".join(lines))
        return self._reply(
            "top_products",
            content,
            tool_calls=[
                {
                    "tool": "aggregate_records",
                    "model": "sale.order.line",
                    "fields": ["product_id", "product_uom_qty:sum"],
                    "groupby": ["product_id"],
                    "result": groups,
                }
            ],
        )

    def _handle_generic(self, message):
        content = _(
            "I'm running in mock mode. I can help with invoices, customers, or top selling products. "
            "You said: \"%(message)s\"",
            message=message,
        )
        return self._reply("generic", content, tool_calls=[])

    def _reply(self, intent, content, tool_calls):
        return content, {
            "provider": "mock",
            "intent": intent,
            "tool_calls": tool_calls,
        }
