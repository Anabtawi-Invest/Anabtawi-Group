/** @odoo-module **/

import { Component, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class QuotationRefreshComponent extends Component {
    setup() {
        const busService = useService("bus_service");

        onMounted(() => {
            console.log(" QuotationRefreshComponent Mounted");

            busService.addChannel("quotation_refresh");
            busService.startPolling();

            busService.addEventListener("notification", (ev) => {
                for (const notif of ev.detail) {
                    if (
                        notif.channel === "quotation_refresh" &&
                        notif.payload.event === "refresh_quotation_page" &&
                        notif.payload.message.refresh
                    ) {
                        console.log(" Bus Message Received: Reloading...");
                        window.location.reload();
                    }
                }
            });
        });
    }
}

QuotationRefreshComponent.template = "whatsapp_api_odoo03.QuotationRefreshComponent";
registry.category("main_components").add("QuotationRefreshComponent", QuotationRefreshComponent);
