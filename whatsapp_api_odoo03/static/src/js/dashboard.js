/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

class Go4WhatsappDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification"),

        this.state = useState({
            user_name: "",
            user_email: "",
            user_mobile_no: "",
            is_api_active: false,
            

            steps: {
                step1: false,
                step2: false,
                step3: false,
                step4: false,
                step5: false,
            },
        });

        onWillStart(async () => {
            const params = await this.orm.call(
                "ir.config_parameter",
                "get_multi_params",
                [[
                    "user_name",
                    "user_email",
                    "user_mobile_no",
                    "whatsapp.is_api_active",
                    "whatsapp.start_messaging",
                    "whatsapp.green_tick",
                ]]
            );

            this.state.user_name = params.user_name || "";
            this.state.user_email = params.user_email || "";
            this.state.user_mobile_no = params.user_mobile_no || "";
            this.state.is_api_active = params["whatsapp.is_api_active"] === "True";

            /* ---------- STEP LOGIC ---------- */

            // Step 1: Registered
            this.state.steps.step1 = !!this.state.user_name;

            // Step 2: Meta verified
            this.state.steps.step2 = params["whatsapp.is_api_active"] === "True";

            // Step 3: API obtained
            this.state.steps.step3 = params["whatsapp.is_api_active"] === "True";

            // Step 4: Broadcasting enabled
            this.state.steps.step4 = params["whatsapp.start_messaging"] === "True";

            // Step 5: Green tick
            this.state.steps.step5 = params["whatsapp.green_tick"] || "notverify";

            
        });
    }
    
    openTemplatesWizrds() {
        this.env.services.action.doAction(
            "whatsapp_api_odoo03.action_whatsapp_template"
        );
    }

    async applyforgreentick() {
        // if (this.state.steps.step5 === "pending") {
        //     return;
        // }

        const result = await this.orm.call(
            "ir.config_parameter",
            "SendVerifiedemail",
            []
        );

        if (result && result.ErrorMessage) {
            this.env.services.notification.add(
                result.ErrorMessage,
                { type: result.ErrorCode === 200 ? 'warning' : 'danger' }
            );
        }
    }

    openCreateTemplatesWizrds() {
        this.env.services.action.doAction({
        type: "ir.actions.act_window",
        res_model: "whatsapp.template",
        views: [[false, "form"]],
        target: "current",
        });
    }

    openPaymentWizrds() {
        this.env.services.action.doAction(
            "whatsapp_api_odoo03.wallet_recharge_list"
        );
    }

    openTriggerPointWizrds() {
        this.env.services.action.doAction(
            "whatsapp_api_odoo03.action_whatsapp_trigger"
        );
    }

    openTriggerPointformWizrds() {
        this.env.services.action.doAction({
        type: "ir.actions.act_window",
        res_model: "whatsapp.trigger",
        views: [[false, "form"]],
        target: "current",
        });
    }

    opensettingpage() {
    this.env.services.action.doAction({
        type: "ir.actions.act_window",
        name: "Settings",
        res_model: "res.config.settings",
        views: [[false, "form"]],
        target: "current",
        context: {
            module: "whatsapp_api_odoo03",
        },
    });
}
}

Go4WhatsappDashboard.template = "whatsapp_api_odoo03.Welcome";

registry.category("actions").add(
    "go4whatsapp_dashboard",
    Go4WhatsappDashboard
);
