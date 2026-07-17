# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class AiAgentLocalMemoryBridge(models.Model):
    """Extends the real Odoo Enterprise ai.agent (verified against
    /home/odoo/src/enterprise/ai/models/ai_agent.py on the customer's own
    Odoo.sh instance) so that native Ask AI questions are checked against
    AI Reporting's Local Memory before any LLM call is made.

    This model only ever loads on a database where the real "ai" app is
    installed, because this whole addon is auto_install=True and depends on
    both ai_reporting and ai -- see __manifest__.py. That is what makes
    `_inherit = "ai.agent"` safe here: on a database without the Enterprise
    AI app, this addon is simply never installed, so this class never loads
    and ai.agent is never referenced.

    _generate_response_for_channel(self, mail_message, channel) is the real
    per-message entry point (confirmed in ai_agent.py): it parses the user's
    prompt, calls _generate_response() which hits the configured LLM
    provider, then posts each returned string via _post_ai_response(). We
    intercept before the LLM call and, only on a confirmed Local Memory
    match, post our own answer and skip calling super() entirely -- so a
    matched question never needs an LLM/API key at all. Any failure or
    non-match falls straight through to native behavior unchanged.
    """

    _inherit = "ai.agent"

    def _generate_response_for_channel(self, mail_message, channel):
        self.ensure_one()
        reply = self._ai_reporting_local_memory_reply(mail_message)
        if reply:
            self._post_ai_response(channel, reply)
            return
        return super()._generate_response_for_channel(mail_message, channel)

    def _ai_reporting_local_memory_reply(self, mail_message):
        if not self._ai_reporting_lma_enabled():
            return False
        try:
            prompt, _session_info_context = self._parse_user_message(mail_message)
        except Exception:
            _logger.exception("AI Reporting: could not parse the Ask AI message; falling back to native AI.")
            return False
        if not prompt or not prompt.strip():
            return False
        memory_service = self.env["ai.reporting.memory_service"]
        try:
            resolved = memory_service.resolve_question(prompt)
        except Exception:
            _logger.exception("AI Reporting: Local Memory lookup failed; falling back to native AI.")
            return False
        if not resolved.get("memory"):
            return False
        try:
            result = memory_service.answer_question(prompt)
        except Exception:
            _logger.exception("AI Reporting: Local Memory answer execution failed; falling back to native AI.")
            return False
        if not isinstance(result, dict):
            return False
        bridge = self.env["ai.reporting.odoo_ai_bridge"]
        if result.get("comparison"):
            return bridge.format_local_memory_comparison_reply(prompt, result)
        if "rows" not in result:
            # answer_question() falls through to ask_native_provider() when there
            # is no real memory match; that shape has no "rows" key, so treat it
            # as "no local answer" and let native Ask AI handle it normally.
            return False
        return bridge.format_local_memory_chat_reply(prompt, result)

    def _ai_reporting_lma_enabled(self):
        value = self.env["ir.config_parameter"].sudo().get_param("ai_reporting.enable_native_ask_ai_lma", "True")
        return str(value).strip().lower() not in ("", "0", "false", "none")
