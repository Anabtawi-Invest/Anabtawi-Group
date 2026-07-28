import json
import os

import requests

from odoo import _, models
from odoo.exceptions import UserError


class AiReportingThirdPartyAiProvider(models.AbstractModel):
    _name = "ai.reporting.third_party_ai_provider"
    _description = "AI Reporting Third Party AI Provider"

    _openai_url = "https://api.openai.com/v1/responses"
    _anthropic_url = "https://api.anthropic.com/v1/messages"

    def get_status(self):
        provider = self._param("ai_reporting.third_party_provider", "none")
        status = {
            "provider": provider,
            "available": False,
            "configured": False,
            "model": False,
            "missing": [],
        }
        if provider == "openai":
            env_name = self._param("ai_reporting.openai_api_key_env", "OPENAI_API_KEY")
            model = self._param("ai_reporting.openai_model", "")
            status.update({
                "available": True,
                "configured": bool(os.environ.get(env_name)),
                "model": model,
                "api_key_env": env_name,
            })
        elif provider == "anthropic":
            env_name = self._param("ai_reporting.anthropic_api_key_env", "ANTHROPIC_API_KEY")
            model = self._param("ai_reporting.anthropic_model", "claude-sonnet-5")
            status.update({
                "available": True,
                "configured": bool(os.environ.get(env_name)),
                "model": model,
                "api_key_env": env_name,
            })
        if status["available"] and not status["configured"]:
            status["missing"].append(status["api_key_env"])
        return status

    def generate_report_definition(self, question, current_definition=None, adjustment=None):
        status = self.get_status()
        if not status["configured"]:
            return False
        system_prompt = self._report_system_prompt()
        prompt = self._report_prompt(question, current_definition=current_definition, adjustment=adjustment)
        if status["provider"] == "openai":
            return self._generate_openai_json(system_prompt, prompt, self._report_schema())
        if status["provider"] == "anthropic":
            return self._generate_anthropic_json(system_prompt, prompt, self._report_schema())
        return False

    def answer_question(self, question, parameters=None):
        status = self.get_status()
        if not status["configured"]:
            return {
                "provider_called": False,
                "answer": _("No third-party AI provider is configured."),
                "status": status,
            }
        system_prompt = _(
            "You are an Odoo business-data assistant. Return concise business answers. "
            "Do not propose SQL, Python, JavaScript, shell commands, URLs, or unsafe actions."
        )
        prompt = json.dumps({
            "question": question,
            "parameters": parameters or {},
        }, ensure_ascii=False, sort_keys=True)
        if status["provider"] == "openai":
            result = self._call_openai(system_prompt, prompt)
        elif status["provider"] == "anthropic":
            result = self._call_anthropic(system_prompt, prompt)
        else:
            return {"provider_called": False, "answer": _("Unsupported provider."), "status": status}
        result.update({"provider_called": True, "provider_name": status["provider"]})
        return result

    def _generate_openai_json(self, system_prompt, prompt, schema):
        result = self._call_openai(system_prompt, prompt, json_schema=schema)
        parsed = self._parse_json(result.get("content"))
        if not parsed:
            return False
        parsed.setdefault("provider_metadata", {})
        parsed["provider_metadata"].update({
            "provider": "openai",
            "model": result.get("model"),
            "input_tokens": result.get("input_tokens", 0),
            "output_tokens": result.get("output_tokens", 0),
        })
        return parsed

    def _generate_anthropic_json(self, system_prompt, prompt, schema):
        tool = {
            "name": "create_odoo_report_definition",
            "description": (
                "Create one safe Odoo report definition for the user request. "
                "Return only fields supported by the schema. Odoo will validate every model, "
                "field, domain, measure, and limit before execution."
            ),
            "input_schema": schema,
        }
        result = self._call_anthropic(
            system_prompt,
            prompt,
            tools=[tool],
            tool_choice={"type": "tool", "name": "create_odoo_report_definition"},
        )
        parsed = result.get("tool_input") or self._parse_json(result.get("content"))
        if not parsed:
            return False
        parsed.setdefault("provider_metadata", {})
        parsed["provider_metadata"].update({
            "provider": "anthropic",
            "model": result.get("model"),
            "input_tokens": result.get("input_tokens", 0),
            "output_tokens": result.get("output_tokens", 0),
        })
        return parsed

    def _call_openai(self, system_prompt, prompt, json_schema=None):
        status = self.get_status()
        env_name = status.get("api_key_env") or "OPENAI_API_KEY"
        if not status.get("model"):
            raise UserError(_(
                "Set the OpenAI model to use in Settings > AI Reporting before enabling the OpenAI provider. "
                "Odoo Reporting does not guess a model name for you."
            ))
        payload = {
            "model": status.get("model"),
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "store": False,
        }
        if json_schema:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "odoo_report_definition",
                    "schema": json_schema,
                }
            }
        response = requests.post(
            self._openai_url,
            headers={
                "Authorization": "Bearer %s" % os.environ[env_name],
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self._timeout(),
        )
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage") or {}
        return {
            "content": self._extract_openai_text(data),
            "model": data.get("model"),
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        }

    def _call_anthropic(self, system_prompt, prompt, tools=None, tool_choice=None):
        status = self.get_status()
        env_name = status.get("api_key_env") or "ANTHROPIC_API_KEY"
        payload = {
            "model": status.get("model") or "claude-sonnet-5",
            "max_tokens": self._max_tokens(),
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
        }
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
        response = requests.post(
            self._anthropic_url,
            headers={
                "x-api-key": os.environ[env_name],
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self._timeout(),
        )
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage") or {}
        text_parts = []
        tool_input = False
        for block in data.get("content", []) or []:
            if block.get("type") == "text":
                text_parts.append(block.get("text") or "")
            elif block.get("type") == "tool_use":
                tool_input = block.get("input") or False
        return {
            "content": "\n".join(part for part in text_parts if part),
            "tool_input": tool_input,
            "model": data.get("model"),
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        }

    def _extract_openai_text(self, data):
        if data.get("output_text"):
            return data["output_text"]
        text_parts = []
        for item in data.get("output", []) or []:
            for content in item.get("content", []) or []:
                if content.get("type") in ("output_text", "text"):
                    text_parts.append(content.get("text") or "")
        return "\n".join(part for part in text_parts if part)

    def _parse_json(self, content):
        if isinstance(content, dict):
            payload = content
        else:
            text = (content or "").strip()
            if text.startswith("```"):
                text = text.strip("`")
                if text.lower().startswith("json"):
                    text = text[4:].strip()
            try:
                payload = json.loads(text)
            except Exception:
                return False
        definition = payload.get("definition", payload)
        if not isinstance(definition, dict) or not definition.get("model"):
            return False
        return {
            "definition": definition,
            "parameters": payload.get("parameters", definition.get("parameters", {})),
        }

    def _report_prompt(self, question, current_definition=None, adjustment=None):
        payload = {
            "question": question,
            "current_definition": current_definition or {},
            "adjustment": adjustment or "",
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _report_system_prompt(self):
        return _(
            "You design safe Odoo 19 advanced report definitions for business users. "
            "Return a JSON object with keys definition and parameters. "
            "Use only Odoo ORM concepts: model, domain, fields, groupby, measures, "
            "calculated_measures, report_type, visualization_type, and limit. "
            "Never include SQL, Python, JavaScript, shell commands, URLs, code, or access bypasses. "
            "Prefer common Odoo business models and simple domains when uncertain."
        )

    def _report_schema(self):
        definition = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "model": {"type": "string"},
                "models": {"type": "array", "items": {"type": "string"}},
                "domain": {"type": "array", "items": {}},
                "fields": {"type": "array", "items": {"type": "string"}},
                "groupby": {"type": "array", "items": {"type": "string"}},
                "measures": {"type": "array", "items": {"anyOf": [{"type": "string"}, {"type": "object"}]}},
                "calculated_measures": {"type": "array", "items": {"type": "object"}},
                "report_type": {"type": "string", "enum": ["table", "pivot", "graph"]},
                "visualization_type": {"type": "string", "enum": ["table", "bar", "line", "pie", "pivot"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 5000},
                "assumptions": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "title",
                "description",
                "model",
                "models",
                "domain",
                "fields",
                "groupby",
                "measures",
                "calculated_measures",
                "report_type",
                "visualization_type",
                "limit",
                "assumptions",
            ],
        }
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "definition": definition,
                "parameters": {"type": "object"},
            },
            "required": ["definition", "parameters"],
        }

    def _param(self, key, default=False):
        return self.env["ir.config_parameter"].sudo().get_param(key, default)

    def _timeout(self):
        return int(self._param("ai_reporting.ai_provider_timeout", 60) or 60)

    def _max_tokens(self):
        return int(self._param("ai_reporting.ai_provider_max_tokens", 3000) or 3000)
