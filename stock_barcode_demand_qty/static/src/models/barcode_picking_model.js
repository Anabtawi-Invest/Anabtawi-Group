import BarcodePickingModel from "@stock_barcode/models/barcode_picking_model";
import { patch } from "@web/core/utils/patch";

patch(BarcodePickingModel.prototype, {
    _demandQtyMode() {
        return Boolean(this.config?.barcode_show_demand_qty);
    },

    _lineDoneQty(line) {
        if (!line) {
            return 0;
        }
        if (typeof this.getQtyDone === "function") {
            return this.getQtyDone(line) || 0;
        }
        return line.qty_done || 0;
    },

    _demandModeLines() {
        const lines = Array.isArray(this.currentState?.lines)
            ? this.currentState.lines
            : Array.isArray(this.pageLines)
            ? this.pageLines
            : [];
        return lines.filter((line) => line && typeof line === "object");
    },

    _demandLineKey(line) {
        if (line.virtual_id != null && line.virtual_id !== false) {
            return `virtual:${line.virtual_id}`;
        }
        if (line.id) {
            return `id:${line.id}`;
        }
        return null;
    },

    _snapshotDemandLines() {
        const snap = new Map();
        for (const line of this._demandModeLines()) {
            const key = this._demandLineKey(line);
            if (!key) {
                continue;
            }
            snap.set(key, {
                qtyDone: this._lineDoneQty(line),
                demandQty: line.demand_qty || 0,
                reservedQty: line.reserved_uom_qty || 0,
                picked: Boolean(line.picked),
            });
        }
        return snap;
    },

    _markDemandLineDirty(line) {
        if (typeof this._markLineAsDirty === "function") {
            this._markLineAsDirty(line);
        }
        line.dirty = true;
    },

    _setLineDemand(line, demand) {
        line.demand_qty = demand;
        line.reserved_uom_qty = demand;
        this._markDemandLineDirty(line);
    },

    _restoreLineDone(line, qtyDone, picked) {
        line.qty_done = qtyDone;
        line.picked = qtyDone ? Boolean(picked) : false;
        this._markDemandLineDirty(line);
    },

    /**
     * Move a quantity that a product scan added to qty_done onto demand_qty.
     * +1 / +5 call updateLine outside a scan, so they still change done quantity.
     */
    _scanArgsAsDemand(line, args) {
        const previousDone = this._lineDoneQty(line);
        const delta = args.qty_done - previousDone;
        if (!(delta > 0)) {
            return args;
        }
        const base = line.demand_qty || line.reserved_uom_qty || 0;
        this._setLineDemand(line, base + delta);
        return { ...args, qty_done: previousDone };
    },

    _applyScannedQtyToDemand(before) {
        if (!before) {
            return;
        }
        for (const line of this._demandModeLines()) {
            const key = this._demandLineKey(line);
            const prev = key ? before.get(key) : null;
            const done = this._lineDoneQty(line);
            if (!prev) {
                if (done > 0) {
                    const already = line.demand_qty || 0;
                    if (already < done) {
                        this._setLineDemand(line, done);
                    }
                    this._restoreLineDone(line, 0, false);
                }
                continue;
            }
            const doneDelta = done - prev.qtyDone;
            const demandDelta = (line.demand_qty || 0) - prev.demandQty;
            if (doneDelta > 0 && demandDelta < doneDelta) {
                const base = demandDelta > 0
                    ? line.demand_qty
                    : prev.demandQty || prev.reservedQty || line.demand_qty || 0;
                this._setLineDemand(line, base + (doneDelta - Math.max(demandDelta, 0)));
                this._restoreLineDone(line, prev.qtyDone, prev.picked);
            } else if (doneDelta > 0) {
                this._restoreLineDone(line, prev.qtyDone, prev.picked);
            }
        }
    },

    async _duringDemandScan(callback) {
        if (!this._demandQtyMode() || this._applyScanToDemand) {
            return callback();
        }
        this._demandScanBefore = this._snapshotDemandLines();
        this._applyScanToDemand = true;
        try {
            return await callback();
        } finally {
            try {
                this._applyScannedQtyToDemand(this._demandScanBefore);
                this.trigger?.("update");
            } finally {
                this._applyScanToDemand = false;
                this._demandScanBefore = null;
            }
        }
    },

    async _beforeDemandScanSave() {
        if (this._applyScanToDemand && this._demandScanBefore) {
            this._applyScannedQtyToDemand(this._demandScanBefore);
            this._demandScanBefore = this._snapshotDemandLines();
        }
    },

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
            if (!(line.qty_done > 0)) {
                values.quantity = 0;
                values.qty_done = 0;
                values.picked = false;
            }
        }
        return values;
    },

    async updateLine(line, args) {
        if (
            this._applyScanToDemand &&
            args &&
            typeof args === "object" &&
            args.qty_done != null
        ) {
            return super.updateLine(line, this._scanArgsAsDemand(line, args));
        }
        return super.updateLine(...arguments);
    },

    async processBarcode() {
        if (typeof super.processBarcode !== "function") {
            return;
        }
        if (!this._demandQtyMode() || this._applyScanToDemand) {
            return super.processBarcode(...arguments);
        }
        return this._duringDemandScan(() => super.processBarcode(...arguments));
    },

    async _processBarcode() {
        if (typeof super._processBarcode !== "function") {
            return;
        }
        if (!this._demandQtyMode() || this._applyScanToDemand) {
            return super._processBarcode(...arguments);
        }
        return this._duringDemandScan(() => super._processBarcode(...arguments));
    },

    async save() {
        if (typeof super.save !== "function") {
            return;
        }
        await this._beforeDemandScanSave();
        return super.save(...arguments);
    },

    async _save() {
        if (typeof super._save !== "function") {
            return;
        }
        await this._beforeDemandScanSave();
        return super._save(...arguments);
    },
});
