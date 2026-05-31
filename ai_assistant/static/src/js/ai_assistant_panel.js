/** @odoo-module **/

import {
    Component,
    onMounted,
    onPatched,
    onWillUnmount,
    useRef,
    useState,
} from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { formatDate, formatDateTime } from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { rpc } from "@web/core/network/rpc";

const { DateTime } = luxon;

function nextMessageId() {
    return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

export class AiAssistantPanel extends Component {
    static template = "ai_assistant.Panel";
    static props = {
        isMinimized: Boolean,
        onClose: Function,
        onToggleMinimize: Function,
    };

    setup() {
        this.messagesContainerRef = useRef("messagesContainer");
        this.inputRef = useRef("messageInput");

        this.state = useState({
            messages: [],
            inputValue: "",
            isLoading: false,
        });

        onMounted(() => this.scrollToBottom());
        onPatched(() => this.scrollToBottom());
    }

    get avatarUrl() {
        return "/ai_assistant/static/description/icon.png";
    }

    get canSend() {
        return this.state.inputValue.trim().length > 0 && !this.state.isLoading;
    }

    get groupedItems() {
        const items = [];
        let lastDayKey = null;
        for (const message of this.state.messages) {
            const dayKey = this.getDayKey(message.timestamp);
            if (dayKey !== lastDayKey) {
                items.push({
                    type: "date",
                    id: `date_${dayKey}`,
                    label: this.formatDayLabel(message.timestamp),
                });
                lastDayKey = dayKey;
            }
            items.push({ type: "message", id: message.id, message });
        }
        return items;
    }

    getDayKey(timestamp) {
        return DateTime.fromMillis(timestamp).toISODate();
    }

    formatDayLabel(timestamp) {
        return formatDate(DateTime.fromMillis(timestamp));
    }

    formatMessageTime(timestamp) {
        return formatDateTime(DateTime.fromMillis(timestamp), {
            format: localization.timeFormat,
        });
    }

    scrollToBottom() {
        if (this.props.isMinimized) {
            return;
        }
        const container = this.messagesContainerRef.el;
        if (container) {
            container.scrollTop = container.scrollHeight;
        }
    }

    buildHistory() {
        return this.state.messages
            .filter((m) => m.role === "user" || m.role === "assistant")
            .map((m) => ({ role: m.role, content: m.content }));
    }

    onInputKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.onSendMessage();
        }
    }

    async onSendMessage() {
        const content = this.state.inputValue.trim();
        if (!content || this.state.isLoading) {
            return;
        }

        const history = this.buildHistory();
        this.state.messages.push({
            id: nextMessageId(),
            role: "user",
            content,
            timestamp: Date.now(),
        });
        this.state.inputValue = "";
        this.state.isLoading = true;

        try {
            const result = await rpc("/ai_assistant/chat", {
                message: content,
                history,
            });
            if (result.success) {
                this.state.messages.push({
                    id: nextMessageId(),
                    role: "assistant",
                    content: result.content,
                    timestamp: Date.now(),
                });
            } else {
                this._pushErrorMessage(result.error);
            }
        } catch {
            this._pushErrorMessage(
                _t("Could not reach the server. Please check your connection and try again.")
            );
        } finally {
            this.state.isLoading = false;
            this.inputRef.el?.focus();
        }
    }

    _pushErrorMessage(errorText) {
        this.state.messages.push({
            id: nextMessageId(),
            role: "assistant",
            content: errorText,
            timestamp: Date.now(),
            isError: true,
        });
    }

    onAttachmentClick() {
        // Placeholder for future attachment support.
    }
}
