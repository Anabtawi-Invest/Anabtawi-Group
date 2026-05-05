/** @odoo-module **/

import { TimeOffCard } from "@hr_holidays/dashboard/time_off_card";
import { formatNumber } from "@hr_holidays/views/hooks";
import { patch } from "@web/core/utils/patch";
import { user } from "@web/core/user";

patch(TimeOffCard.prototype, {
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
