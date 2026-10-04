import { patch } from "@web/core/utils/patch";
import { CategorySelector } from "@point_of_sale/app/components/category_selector/category_selector";

patch(CategorySelector.prototype, {
    getCategoriesAndSub() {
        const hiddenIds = new Set(
            this.pos.models["pos.category"].filter((c) => c.hide_in_pos_ui).map((c) => c.id)
        );
        return super.getCategoriesAndSub().filter((c) => !hiddenIds.has(c.id));
    },
});
