/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { ActionMenus } from "@web/search/action_menus/action_menus";




patch(ActionMenus.prototype, {

    async loadPrintItems() {



        await super.loadPrintItems(...arguments);


        if (!this.state.printItems || this.state.printItems.length === 0) {

            return;
        }




        const originalPrintItems = [...this.state.printItems];


        const actionIds = originalPrintItems
            .filter(item => item.action && item.action.id)
            .map(item => item.action.id);




        const reportConfigs = await this.orm.call(
            "ir.actions.report",
            "read",
            [actionIds],
            {
                fields: ["id", "auto_print_enabled", "default_printer_id"],
            }
        );
        console.log("[Direct Print] Report configs loaded:", reportConfigs);


        const configMap = {};
        reportConfigs.forEach(config => {
            configMap[config.id] = config;
        });


        const directPrintItems = [];

        originalPrintItems.forEach((printItem, index) => {
            if (!printItem.action || !printItem.action.id) return;

            const actionId = printItem.action.id;
            const config = configMap[actionId];
            console.log(`[Direct Print] Checking item: ${printItem.description}, Config:`, config);


            if (config && config.auto_print_enabled) {


                directPrintItems.push({
                    key: `dp_${printItem.key}`,
                    description: `${printItem.description} (Direct Print)`,
                    class: printItem.class,
                    action: printItem.action,
                    callback: async () => {

                        try {
                            console.log(`[Direct Print] Callback triggered for: ${printItem.description}, Action ID: ${actionId}`);
                            this.env.services.notification.add(
                                `Sending "${printItem.description}" to printer...`,
                                { type: "info" }
                            );

                            const activeIds = this.props.getActiveIds();
                            const activeModel = this.props.resModel;


                            const fullAction = await this.orm.call(
                                "ir.actions.report",
                                "read",
                                [[actionId]],
                                {
                                    fields: ["name", "report_name", "report_type"],
                                }
                            );

                            if (!fullAction || fullAction.length === 0) {
                                throw new Error("Report action not found");
                            }

                            const reportAction = fullAction[0];

                            const reportUrl = `/report/pdf/${reportAction.report_name}/${activeIds.join(',')}`;


                            const context = {
                                active_ids: activeIds,
                                active_model: activeModel,
                                direct_print_mode: true,
                            };
                            console.log("[Direct Print] Fetching report URL:", reportUrl, "with Context:", context);



                            const response = await fetch(reportUrl + `?context=${encodeURIComponent(JSON.stringify(context))}`, {
                                method: 'GET',
                                headers: {
                                    'Content-Type': 'application/json',
                                },
                            });



                            if (response.ok) {
                                const result = await response.json();
                                console.log("[Direct Print] Target server response OK:", result);

                                this.env.services.notification.add(
                                    result.message || `"${printItem.description}" sent to printer successfully!`,
                                    { type: "success" }
                                );


                            } else {
                                console.error("[Direct Print] HTTP Error:", response.status, response.statusText);
                                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                            }
                        } catch (error) {
                            console.error("[Direct Print] Error caught in callback:", error);
                            this.env.services.notification.add(
                                `Failed to send "${printItem.description}" to printer: ${error.message}`,
                                { type: "danger", sticky: true }
                            );
                        }
                    },
                });
            }
        });




        if (directPrintItems.length > 0) {
            this.state.printItems.push(...directPrintItems);
        }


    },
});

