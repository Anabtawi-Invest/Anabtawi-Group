import BarcodePickingModel from "@stock_barcode/models/barcode_picking_model";
import { patch } from "@web/core/utils/patch";

patch(BarcodePickingModel.prototype, {
    _getMoveLineData(id) {
        const smlData = super._getMoveLineData(...arguments);
        if (this.config.barcode_show_demand_qty && smlData.demand_qty) {
            smlData.reserved_uom_qty = smlData.demand_qty;
            if (!smlData.picked) {
                smlData.qty_done = 0;
            }
        }
        return smlData;
    },

    displayLineQtyDemand(line) {
        if (!this.config.barcode_show_demand_qty) {
            return super.displayLineQtyDemand(...arguments);
        }
        return this.getQtyDemand(line) > 0;
    },

    _getNewLineDefaultContext() {
        const context = super._getNewLineDefaultContext(...arguments);
        if (this.config.barcode_show_demand_qty) {
            context.default_qty_done = 0;
            delete context.force_fullfil_quantity;
        }
        return context;
    },

    _createCommandVals(line) {
        const values = super._createCommandVals(...arguments);
        if (this.config.barcode_show_demand_qty) {
            values.demand_qty = line.demand_qty || line.reserved_uom_qty || 0;
        }
        return values;
    },
});
