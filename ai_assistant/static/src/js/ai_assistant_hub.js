/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { AiAssistantPanel } from "@ai_assistant/js/ai_assistant_panel";

export class AiAssistantHub extends Component {
    static template = "ai_assistant.Hub";
    static components = { AiAssistantPanel };

    setup() {
        this.state = useState({
            isOpen: false,
            isMinimized: false,
        });
    }

    get showPanel() {
        return this.state.isOpen;
    }

    get showBubble() {
        return !this.state.isOpen;
    }

    onBubbleClick() {
        this.state.isOpen = true;
        this.state.isMinimized = false;
    }

    onClose() {
        this.state.isOpen = false;
        this.state.isMinimized = false;
    }

    onToggleMinimize() {
        this.state.isMinimized = !this.state.isMinimized;
    }
}
