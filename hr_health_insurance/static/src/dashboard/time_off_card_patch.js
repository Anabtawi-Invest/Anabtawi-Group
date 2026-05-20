/** @odoo-module **/

import { TimeOffCard } from "@hr_holidays/dashboard/time_off_card";
import { formatNumber } from "@hr_holidays/views/hooks";
import { patch } from "@web/core/utils/patch";
import { user } from "@web/core/user";
import { onWillRender } from "@odoo/owl";

const warnedMissingHoursPerDay = new Set();

patch(TimeOffCard.prototype, {
    setup() {
        super.setup(...arguments);
        onWillRender(() => {
            const d = this.props?.data;
            if (!d || d.request_unit !== "hour") {
                return;
            }
            const key = this.props.holidayStatusId ?? "unknown";
            if (!d.hours_per_day) {
                if (!warnedMissingHoursPerDay.has(key)) {
                    warnedMissingHoursPerDay.add(key);
                    console.warn(
                        "[hr_health_insurance TimeOff] request_unit is hour but `hours_per_day` is missing in RPC payload. " +
                            "Usually: module backend not upgraded on this DB, or get_allocation_data inheritance not loaded. " +
                            "Sample keys:",
                        Object.keys(d)
                    );
                }
                return;
            }
        });
    },
    getEquivalentDaysDisplay() {
        const { data, requires_allocation } = this.props;
        const hpd = data?.hours_per_day;
        if (!data || data.request_unit !== "hour" || !hpd) {
            return "";
        }
        const duration = requires_allocation
            ? data.virtual_remaining_leaves
            : data.virtual_leaves_taken;
        return formatNumber(user.lang, duration / hpd);
    },
});

console.info(
    "[hr_health_insurance TimeOff] assets loaded: TimeOffCard patched. If you do not see this in the browser console, the module assets are not on this deployment."
);
