import { Message } from "@mail/core/common/message_model";
import { fields } from "@mail/core/common/record";

import { patch } from "@web/core/utils/patch";

patch(Message.prototype, {
    setup() {
        super.setup(...arguments);
        /** @type {string|undefined} */
        this.acting_employee_name = fields.Attr();
    },

    /**
     * Show acting employee beside the username when present.
     * Example: "Admin User (Ahmed Mohamed)"
     */
    get authorName() {
        const name = super.authorName;
        if (this.acting_employee_name) {
            return `${name} (${this.acting_employee_name})`;
        }
        return name;
    },
});
