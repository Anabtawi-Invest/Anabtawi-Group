import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {
    isProductInHiddenCategory(product) {
        const categories = product.pos_categ_ids || [];
        return categories.length > 0 && categories.every((c) => c.hide_in_pos_ui);
    },

    filterExcludedProducts(products) {
        const isBrowsing = !this.searchProductWord?.trim() && !this.selectedCategory?.id;
        if (isBrowsing) {
            products = this._skipHiddenCategoryProducts(products);
        }
        return super.filterExcludedProducts(products);
    },

    *_skipHiddenCategoryProducts(products) {
        for (const product of products) {
            if (!this.isProductInHiddenCategory(product)) {
                yield product;
            }
        }
    },
});
