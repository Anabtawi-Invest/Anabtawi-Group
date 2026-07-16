"""Soft integration with the optional OCA ``ai_tool`` addon.

``ai_tool`` (https://github.com/OCA/ai/tree/18.0/ai_tool) is a small, technical
addon that lets any Odoo model expose whitelisted methods as AI-callable
"tools" with a typed input/output JSON schema, discoverable by MCP servers or
other agent frameworks through its ``ai.tool`` model:

    name            Char, required
    description     Text
    model_id        Many2one("ir.model"), required
    function_name   Char, required
    kind            Selection: generic / generic_model / record

Its ``aitool`` decorator (``odoo/addons/ai_tool/tools.py``) stamps the
decorated function with ``func._ai_tool = {"input_schema": ..., "output_schema": ...}``,
which ``ai.tool._get_tool_definition()`` reads back when describing the tool.

``ai_tool`` is **not** a dependency of ``ai_reporting`` -- it may or may not be
installed on a given database, and this module must install and work fine
either way (see ``services/odoo_ai_bridge.py`` for the detection/registration
side). This shim re-exports the real decorator when ``ai_tool`` is installed,
and falls back to a no-op decorator when it is not, so the exact same
AI-callable methods on our own models work in both cases -- called directly by
our own code when ``ai_tool`` is absent, and additionally callable by anything
that talks to ``ai.tool`` (MCP servers, automations, or a future native Odoo
AI agent that reuses this convention) when it is present.

Known limitation: because Python decorators are evaluated once when this
module's classes are first loaded, a server process that started before
``ai_tool`` was installed will keep the no-op decorator until the server is
restarted. ``odoo_ai_bridge.register_integration()`` already skips registering
a tool whose function does not carry ``_ai_tool`` yet, rather than registering
it with a missing schema, and will pick it up correctly after the next restart.
"""

try:
    from odoo.addons.ai_tool.tools import aitool  # noqa: F401

    AI_TOOL_AVAILABLE = True
except ImportError:
    AI_TOOL_AVAILABLE = False

    def aitool(input_schema=None, output_schema=None, required_inputs=None):
        def _decorate(func):
            return func

        return _decorate
