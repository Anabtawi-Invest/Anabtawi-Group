import { Message } from "@mail/core/common/message_model";
import { fields } from "@mail/core/common/record";

import { patch } from "@web/core/utils/patch";

patch(Message.prototype, {
    setup() {
        super.setup(...arguments);
        /** @type {string|undefined} */
        this.acting_employee_name = fields.Attr();
        /** @type {string|undefined} */
        this.acting_branch_name = fields.Attr();
    },

    /**
     * Show acting employee or branch beside the username when present.
     * Example: "Admin User (Ahmed Mohamed)" or "Admin User (Branch A)"
     */
    get authorName() {
        const name = super.authorName;
        const actingName = this.acting_branch_name || this.acting_employee_name;
        if (actingName) {
            return `${name} (${actingName})`;
        }
        return name;
    },
});
