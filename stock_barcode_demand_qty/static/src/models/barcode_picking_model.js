import BarcodePickingModel from "@stock_barcode/models/barcode_picking_model";
import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";

patch(BarcodePickingModel.prototype, {
    _demandQtyMode() {
        return Boolean(this.config?.barcode_show_demand_qty);
    },

    _demandLocked() {
        return Boolean(this.record?.barcode_demand_locked);
    },

    _branchDemandOpen() {
        return this._demandQtyMode() && !this._demandLocked();
    },

    _factoryQtyOpen() {
        return this._demandQtyMode() && this._demandLocked();
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
        if (this._demandQtyMode()) {
            smlData.reserved_uom_qty = smlData.demand_qty || 0;
            if (!smlData.picked) {
                smlData.qty_done = 0;
            }
        }
        return smlData;
    },

    getQtyDemand(line) {
        if (this._demandQtyMode()) {
            return line?.demand_qty || 0;
        }
        return super.getQtyDemand(...arguments);
    },

    getIncrementQuantity(line) {
        if (this._branchDemandOpen()) {
            return 1;
        }
        return super.getIncrementQuantity(...arguments);
    },

    lineIsFaulty(line) {
        if (this._demandQtyMode()) {
            return false;
        }
        return super.lineIsFaulty(...arguments);
    },

    _shouldCreateLineOnExceed(line) {
        if (this._factoryQtyOpen()) {
            return false;
        }
        return super._shouldCreateLineOnExceed(...arguments);
    },

    displayLineQtyDemand(line) {
        if (!this.config.barcode_show_demand_qty) {
            return super.displayLineQtyDemand(...arguments);
        }
        return this.getQtyDemand(line) > 0;
    },

    _getNewLineDefaultContext() {
        const context = super._getNewLineDefaultContext(...arguments);
        if (this._branchDemandOpen()) {
            context.default_qty_done = 0;
            delete context.force_fullfil_quantity;
        }
        return context;
    },

    _getNewLineDefaultValues(fieldsParams) {
        const values = super._getNewLineDefaultValues(...arguments);
        if (this._factoryQtyOpen()) {
            values.demand_qty = 0;
            values.picked = true;
        }
        if (this._branchDemandOpen()) {
            values.qty_done = 0;
            values.picked = false;
        }
        return values;
    },

    _getFieldToWrite() {
        const fields = super._getFieldToWrite(...arguments);
        if (this._demandQtyMode() && !fields.includes("demand_qty")) {
            fields.push("demand_qty");
        }
        return fields;
    },

    _createCommandVals(line) {
        const values = super._createCommandVals(...arguments);
        if (!this._demandQtyMode()) {
            return values;
        }
        if (this._demandLocked()) {
            values.demand_qty = line.demand_qty || 0;
            values.quantity = line.qty_done || 0;
            values.picked = Boolean(line.picked || line.qty_done > 0);
            return values;
        }
        values.demand_qty = line.demand_qty || 0;
        values.quantity = 0;
        values.qty_done = 0;
        values.picked = false;
        return values;
    },

    async updateLine(line, args) {
        if (
            this._branchDemandOpen() &&
            !this._applyScanToDemand &&
            args &&
            typeof args === "object" &&
            typeof args.qty_done === "number" &&
            args.qty_done !== 0
        ) {
            const base = line.demand_qty || 0;
            this._setLineDemand(line, Math.max(0, base + args.qty_done));
            args = { ...args, qty_done: 0 };
        }
        if (
            this._factoryQtyOpen() &&
            args &&
            typeof args === "object" &&
            typeof args.qty_done === "number" &&
            args.qty_done !== 0
        ) {
            line.picked = true;
        }
        if (
            this._applyScanToDemand &&
            args &&
            typeof args === "object" &&
            args.qty_done != null
        ) {
            return super.updateLine(line, this._scanArgsAsDemand(line, args));
        }
        return super.updateLine(line, args);
    },

    async processBarcode() {
        if (typeof super.processBarcode !== "function") {
            return;
        }
        if (!this._branchDemandOpen() || this._applyScanToDemand) {
            return super.processBarcode(...arguments);
        }
        return this._duringDemandScan(() => super.processBarcode(...arguments));
    },

    async _processBarcode() {
        if (typeof super._processBarcode !== "function") {
            return;
        }
        if (!this._branchDemandOpen() || this._applyScanToDemand) {
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

    get displayValidateButton() {
        if (this._branchDemandOpen()) {
            return false;
        }
        return super.displayValidateButton;
    },

    get displayConfirmDemandButton() {
        return Boolean(
            this._branchDemandOpen() &&
            this.config?.barcode_can_confirm_demand &&
            !this.isDone &&
            !this.isCancelled
        );
    },

    get displayEditDemandButton() {
        return Boolean(
            this._factoryQtyOpen() &&
            this.config?.barcode_can_confirm_demand &&
            !this.isDone &&
            !this.isCancelled &&
            !this._factoryHasEnteredQty()
        );
    },

    get displayDemandConfirmMessage() {
        return Boolean(this._branchDemandOpen() && !this.isDone && !this.isCancelled);
    },

    _factoryHasEnteredQty() {
        const lines = Array.isArray(this.currentState?.lines) ? this.currentState.lines : [];
        return lines.some((line) => line && line.product_id && line.picked);
    },

    _demandErrorMessage(error) {
        const dataMessage = error?.data?.message;
        if (typeof dataMessage === "string" && dataMessage) {
            return dataMessage;
        }
        const argument = error?.data?.arguments?.[0];
        if (typeof argument === "string" && argument) {
            return argument;
        }
        if (typeof error?.message === "string" && error.message) {
            return error.message;
        }
        return "تعذر تنفيذ العملية";
    },

    async _reloadDemandTransfer() {
        const { route, params } = this.getActionRefresh(this.resId);
        const result = await rpc(route, params);
        await this.refreshCache(result.data.records);
        this.trigger?.("update");
    },

    async confirmDemand() {
        if (!this.displayConfirmDemandButton) {
            return;
        }
        try {
            await this.save();
            await this.orm.call("stock.picking", "action_barcode_confirm_demand", [[this.resId]]);
            await this._reloadDemandTransfer();
        } catch (error) {
            this.notification(this._demandErrorMessage(error), { type: "danger" });
        }
    },

    async editDemand() {
        if (!this.displayEditDemandButton) {
            return;
        }
        try {
            await this.save();
            await this.orm.call("stock.picking", "action_barcode_edit_demand", [[this.resId]]);
            await this._reloadDemandTransfer();
        } catch (error) {
            this.notification(this._demandErrorMessage(error), { type: "danger" });
        }
    },
});
