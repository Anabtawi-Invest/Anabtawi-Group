import { registry } from "@web/core/registry";
import { Base } from "@point_of_sale/app/models/related_models";

export class PosPredefinedDiscount extends Base {
    static pythonModel = "pos.predefined.discount";
}

registry.category("pos_available_models").add(PosPredefinedDiscount.pythonModel, PosPredefinedDiscount);

