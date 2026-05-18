/** @odoo-module **/

import { registry } from "@web/core/registry";
import { AiAssistantHub } from "@ai_assistant/js/ai_assistant_hub";

registry.category("main_components").add("ai_assistant.Hub", {
    Component: AiAssistantHub,
});
