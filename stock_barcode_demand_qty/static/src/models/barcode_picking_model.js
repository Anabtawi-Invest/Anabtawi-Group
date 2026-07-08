import BarcodePickingModel from "@stock_barcode/models/barcode_picking_model";
import { patch } from "@web/core/utils/patch";

patch(BarcodePickingModel.prototype, {
    _getMoveLineData(id) {
        const smlData = super._getMoveLineData(...arguments);
        if (smlData.demand_qty) {
            smlData.reserved_uom_qty = smlData.demand_qty;
        }
        return smlData;
    },

    _getNewLineDefaultContext() {
        const context = super._getNewLineDefaultContext(...arguments);
        if (this.selectedLine?.demand_qty) {
            context.force_fullfil_quantity = this.selectedLine.demand_qty;
        }
        return context;
    },

    _createCommandVals(line) {
        const values = super._createCommandVals(...arguments);
        values.demand_qty = line.demand_qty || line.reserved_uom_qty || 0;
        return values;
    },
});
