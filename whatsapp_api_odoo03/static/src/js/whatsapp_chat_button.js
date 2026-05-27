/** @odoo-module **/

import { Component, useState,onWillStart,onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class WhatsAppButton extends Component {
    setup() {
        this.action = useService("action");
        this.orm = useService("orm");

        this.state = useState({
            showPopup: false,
            customers: [],
            selectedCustomer: null,
            messages: [],
            newMessage: "",
            attachment: null, 
            previewFile: null,
            totalUnreadCount: 0,
            searchQuery: "",  // Add search query state
            templates: [],     // ensure defined
            showTemplatePopup: false,  // replace showTemplateList with this
        });
        this.busService = useService("bus_service");
        this.channel = "RefreshwhatsappPage"

        onMounted(() => {
            this.busService.addChannel(this.channel);
            this.updateUnreadCount();
            this.busService.subscribe('notification', this.onNotification.bind(this));
        });

        this.updateUnreadCount();
        this.openPopup = this.openPopup.bind(this);
        this.openChat = this.openChat.bind(this);
        this.goBack = this.goBack.bind(this);
        this.sendMessage = this.sendMessage.bind(this);
        this.onKeydown = this.onKeydown.bind(this);
        this.handleFileChange = this.handleFileChange.bind(this);
        this.removePreview = this.removePreview.bind(this);
    }

    get filteredCustomers() {
    const query = this.state.searchQuery.trim().toLowerCase();
    if (!query) return this.state.customers;
    return this.state.customers.filter(c =>
        (c.name && c.name.toLowerCase().includes(query)) ||
        (c.mobile && c.mobile.toLowerCase().includes(query))
    );
    }

    async scrollToBottom() {
    // Use timeout to ensure DOM is rendered before scrolling
    setTimeout(() => {
        const chatBody = document.getElementById("chatbody");
        if (chatBody) {
            chatBody.scrollTop = chatBody.scrollHeight;
        } else {
            console.warn("⚠️ Chat body not found");
        }
    },100);
}

    async onNotification(payload) {
        if (payload.refresh === true) {
            this.updateUnreadCount();
            this.openChat(this.state.selectedCustomer);
            await this.openPopup(false);
        }
    }

    async updateUnreadCount() {
        // Fetch unread message info
        const unreadMessages = await this.orm.searchRead(
            "whatsapp.chat.message",
            [["read_msg", "=", false], ["is_from_user", "=", false]],
            ["partner_id"]
        );

        // Count total unread messages
        this.state.totalUnreadCount = unreadMessages.length;
    }

    async openPopup(fromNotification = true) {
    if (fromNotification) {
        this.state.showPopup = !this.state.showPopup;
    }

    if (this.state.showPopup || fromNotification) {
        const [customers, messages] = await Promise.all([
            this.orm.searchRead(
                "res.partner",
                [["is_company", "=", false], ["mobile", "!=", false]],
                ["name", "mobile", "image_128", "chatactive", "chat_activated_at"]
            ),
            this.orm.searchRead(
                "whatsapp.chat.message",
                [],
                ["partner_id", "date", "read_msg"]
            ),
        ]);

        const latestMessageMap = {};
        const unreadCountMap = {};

        messages.forEach(msg => {
            const partnerId = msg.partner_id[0];
            const msgDate = new Date(msg.date);
            if (!latestMessageMap[partnerId] || msgDate > latestMessageMap[partnerId]) {
                latestMessageMap[partnerId] = msgDate;
            }
            if (!msg.read_msg) {
                unreadCountMap[partnerId] = (unreadCountMap[partnerId] || 0) + 1;
            }
        });

        const now = new Date();
        const expiredIds = [];

        customers.forEach(cust => {
            cust.unread_count = unreadCountMap[cust.id] || 0;

            if (cust.chat_activated_at) {
                const activatedTime = new Date(cust.chat_activated_at);
                const activatedTimeIST = new Date(activatedTime.getTime() + (5.5 * 60 * 60 * 1000));

                const diffMs = (24 * 60 * 60 * 1000) - (now - activatedTimeIST);

                if (diffMs <= 0) {
                    cust.chatactive = false;
                    cust.chat_active_timer = "Expired";
                    expiredIds.push(cust.id);
                } else {
                    const hours = Math.floor(diffMs / (1000 * 60 * 60));
                    const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
                    cust.chat_active_timer = `${hours}h ${minutes}m left`;
                }
            } else {
                cust.chat_active_timer = "Inactive";
            }

            // Attach latest message date for sorting
            cust.latest_msg_date = latestMessageMap[cust.id] || null;
        });

        //Update expired records in one go
        if (expiredIds.length > 0) {
            await this.orm.write("res.partner", expiredIds, { chatactive: false });
        }

        // Sort by:
        // 1. Active first
        // 2. Then by latest message date (newest first)
        customers.sort((a, b) => {
            if (a.chatactive !== b.chatactive) {
                return a.chatactive ? -1 : 1; // active first
            }

            const dateA = a.latest_msg_date ? new Date(a.latest_msg_date) : new Date(0);
            const dateB = b.latest_msg_date ? new Date(b.latest_msg_date) : new Date(0);
            return dateB - dateA; // latest message first
        });

        this.state.customers = customers;
    }
}


    async openChat(customer) {

        if (!customer || !customer.id) {
            return;
        }

        this.state.selectedCustomer = customer;

        // Find all unread messages for this customer
        const unreadIds = await this.orm.search(
            "whatsapp.chat.message",
            [["partner_id", "=", customer.id], ["read_msg", "=", false]]
        );

        // If any unread messages exist, mark them as read
        if (unreadIds.length > 0) {
            await this.orm.call(
                "whatsapp.chat.message",
                "write",
                [unreadIds, { read_msg: true }]
            );
        }

        //  Reset unread count visually
        customer.unread_count = 0;

        //  Fetch updated messages
        this.state.messages = await this.orm.searchRead(
            "whatsapp.chat.message",
            [["partner_id", "=", customer.id]],
            ["message", "is_from_user", "date", "attachment_name", "attachment_url", "attachment_type", "read_msg", "single_tick","double_tick","read_cust_message"]
        );
        this.scrollToBottom();
        this.updateUnreadCount();
    }

    goBack() {
        this.state.selectedCustomer = null;
        this.state.messages = [];
    }

    handleFileChange(ev) {
        const file = ev.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (e) => {
            const base64 = e.target.result.split(",")[1];
            this.state.attachment = {
                name: file.name,
                content: base64,
                type: file.type,
            };
            this.state.previewFile = {
                name: file.name,
                type: file.type,
                url: e.target.result,
            };
        };
        reader.readAsDataURL(file);
    }

    removePreview() {
        this.state.previewFile = null;
        this.state.attachment = null;
    }

    async sendMessage() {
        if ((!this.state.newMessage && !this.state.attachment) || !this.state.selectedCustomer) return;

        const text = this.state.newMessage.trim();
        const partnerId = this.state.selectedCustomer.id;

        try {
            await this.orm.call("whatsapp.chat.message", "send_chat_message", [
                partnerId,
                text,
                this.state.attachment,
            ]);

            this.state.newMessage = "";
            this.state.attachment = null;
            this.state.previewFile = null;

            await this.openChat(this.state.selectedCustomer);
        } catch (error) {
            console.error("Error sending message:", error);
        }
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && this.state.newMessage.trim() !== "") {
            this.sendMessage();
        }
    }

    async openTemplateList() {
        this.state.showTemplatePopup = !this.state.showTemplatePopup;

        if (this.state.showTemplatePopup && this.state.templates.length === 0) {
            try {
                const templates = await this.orm.searchRead(
                    "whatsapp.template",
                    [],
                    ["template_name", "language", "template_id"]
                );
                this.state.templates = templates;
            } catch (error) {
                console.error("Error fetching templates:", error);
            }
        }
    }

    closeTemplateList() {
        this.state.showTemplatePopup = false;
    }

    sendTemplate = async (tpl) => {
    try {
        console.log("tpl.............", tpl);
        const partnerId = this.state.selectedCustomer.id;

        //  Loader start
        this.state.isLoading = true;
        this.render();

        //  API call
        await this.orm.call("whatsapp.chat.message", "send_template_message", [
            partnerId,
            tpl
        ]);

        //  Close template popup
        this.state.showTemplatePopup = false;

        // Refresh chat
        await this.openChat(this.state.selectedCustomer);
    } catch (error) {
        console.error("Error sending template:", error);
    } finally {
        //  Loader stop
        this.state.isLoading = false;
        this.render();
    }
};



}

WhatsAppButton.template = "whatsapp_api_odoo03.WhatsAppButton";
registry.category("main_components").add("WhatsAppButton", { Component: WhatsAppButton });
