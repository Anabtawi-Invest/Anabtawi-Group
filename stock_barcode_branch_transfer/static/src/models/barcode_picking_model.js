import BarcodePickingModel from "@stock_barcode/models/barcode_picking_model";
import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";

patch(BarcodePickingModel.prototype, {
    _branchLocationOverrideEnabled() {
        if (!this.config?.barcode_override_scanned_locations) {
            return false;
        }
        // Odoo barcode config often stores this as true, not "mandatory".
        const sourceMode = this.config.restrict_scan_source_location;
        return sourceMode === true || sourceMode === "mandatory";
    },

    _barcodeId(value) {
        if (Array.isArray(value)) {
            return value[0] || false;
        }
        if (value && typeof value === "object") {
            return value.id || false;
        }
        return value || false;
    },

    _setBarcodeMany2one(record, fieldName, id, name) {
        if (!record) {
            return;
        }
        const sample = record.location_id ?? record.location_dest_id ?? record.product_id;
        const current = record[fieldName];
        if (
            Array.isArray(sample) ||
            Array.isArray(current) ||
            (sample && typeof sample === "object") ||
            (current && typeof current === "object")
        ) {
            record[fieldName] = id ? [id, name || ""] : false;
            return;
        }
        record[fieldName] = id || false;
    },

    _branchScannedLocation(barcodeData) {
        if (barcodeData?.location && typeof barcodeData.location === "object" && barcodeData.location.id) {
            return barcodeData.location;
        }
        if (barcodeData?.destLocation && typeof barcodeData.destLocation === "object" && barcodeData.destLocation.id) {
            return barcodeData.destLocation;
        }
        if (barcodeData?.sourceLocation && typeof barcodeData.sourceLocation === "object" && barcodeData.sourceLocation.id) {
            return barcodeData.sourceLocation;
        }
        if (barcodeData?.match?.id) {
            return barcodeData.match;
        }
        return null;
    },

    _branchLines() {
        const lines = this.currentState?.lines || this.pageLines || [];
        return Array.isArray(lines) ? lines : [];
    },

    _lineQtyDone(line) {
        if (!line) {
            return 0;
        }
        if (typeof this.getQtyDone === "function") {
            return this.getQtyDone(line) || 0;
        }
        return line.qty_done || line.quantity || 0;
    },

    _branchBarcodeInfoClass() {
        try {
            return this.barcodeInfo?.class || "";
        } catch {
            return "";
        }
    },

    _expectsDestinationScan() {
        const mode = this.config?.restrict_scan_dest_location;
        if (!mode || mode === "no" || mode === false) {
            return false;
        }
        const infoClass = this._branchBarcodeInfoClass();
        if (infoClass.includes("dest")) {
            return true;
        }
        if (
            infoClass.includes("src") ||
            infoClass.includes("source") ||
            infoClass.includes("product") ||
            infoClass.includes("lot") ||
            infoClass.includes("serial") ||
            infoClass.includes("pack")
        ) {
            return false;
        }
        if (mode !== "mandatory" && mode !== true) {
            return infoClass.includes("validate");
        }
        const line = this.selectedLine || this.lastScannedLine;
        return Boolean(line && this._lineQtyDone(line) > 0 && !this.lastScanned?.destLocation);
    },

    _branchScanRole(location, forcedRole) {
        if (forcedRole === "source" || forcedRole === "dest") {
            return forcedRole;
        }
        const lockedSourceId = this._barcodeId(this.record?.barcode_locked_source_location_id);
        const lockedDestId = this._barcodeId(this.record?.barcode_locked_dest_location_id);
        if (!lockedSourceId) {
            return "source";
        }
        if (lockedDestId && location.id === lockedDestId && location.id !== lockedSourceId) {
            return "dest";
        }
        if (location.id === lockedSourceId && location.id !== lockedDestId) {
            return "source";
        }
        const destMode = this.config?.restrict_scan_dest_location;
        if (!destMode || destMode === "no" || destMode === false) {
            return "source";
        }
        return this._expectsDestinationScan() ? "dest" : "source";
    },

    _rpcErrorMessage(error) {
        const dataMessage = error?.data?.message;
        if (typeof dataMessage === "string" && dataMessage) {
            return dataMessage;
        }
        const argument = error?.data?.arguments?.[0];
        if (typeof argument === "string" && argument) {
            return argument;
        }
        if (typeof error?.message === "string" && error.message && !error.message.startsWith("Odoo Server Error")) {
            return error.message;
        }
        return "خطأ: تعذر التحقق من الموقع الممسوح.";
    },

    _notifyBranchError(message) {
        if (typeof this.notification === "function") {
            this.notification(message, { type: "danger" });
        } else {
            this.trigger?.("notification", { message, type: "danger" });
        }
        this.trigger?.("playSound", "error");
    },

    async _branchOrmCall(method, args) {
        const orm = this.orm || this.services?.orm;
        if (orm?.call) {
            return orm.call("stock.picking", method, args);
        }
        return rpc(`/web/dataset/call_kw/stock.picking/${method}`, {
            model: "stock.picking",
            method,
            args,
            kwargs: {},
        });
    },

    _suppressBranchLocationWarnings() {
        if (typeof this.notification !== "function") {
            return () => {};
        }
        const original = this.notification.bind(this);
        this.notification = (message, options) => {
            const type = options?.type;
            if (type === "danger" || type === "warning") {
                return;
            }
            return original(message, options);
        };
        return () => {
            this.notification = original;
        };
    },

    _syncBranchLocations(result, barcodeData) {
        const records = [this.record, this.currentState].filter(Boolean);
        const seen = new Set();
        for (const record of records) {
            if (seen.has(record)) {
                continue;
            }
            seen.add(record);
            this._setBarcodeMany2one(
                record,
                "location_id",
                result.location_id,
                result.location_name
            );
            this._setBarcodeMany2one(
                record,
                "location_dest_id",
                result.location_dest_id,
                result.location_dest_name
            );
            this._setBarcodeMany2one(
                record,
                "barcode_locked_source_location_id",
                result.locked_source_location_id,
                result.locked_source_location_name
            );
            this._setBarcodeMany2one(
                record,
                "barcode_locked_dest_location_id",
                result.locked_dest_location_id,
                result.locked_dest_location_name
            );
        }
        if (result.role === "dest") {
            barcodeData.destLocation = barcodeData.location;
            barcodeData.sourceLocation = false;
            return;
        }
        barcodeData.destLocation = false;
        barcodeData.sourceLocation = barcodeData.location;
    },

    _markBranchLineDirty(line) {
        if (typeof this._markLineAsDirty === "function") {
            this._markLineAsDirty(line);
        }
        line.dirty = true;
    },

    _assignBranchLocation(result, barcodeData) {
        const location = barcodeData.location;
        if (result.role === "source") {
            if (this.lastScanned) {
                this.lastScanned.sourceLocation = location;
            }
            try {
                this.location = location;
            } catch {
                // Some barcode builds expose location as a getter.
            }
        } else if (this.lastScanned) {
            this.lastScanned.destLocation = location;
        }
        const fieldName = result.role === "dest" ? "location_dest_id" : "location_id";
        const locationId = result.role === "dest" ? result.location_dest_id : result.location_id;
        const locationName = result.role === "dest" ? result.location_dest_name : result.location_name;
        for (const line of this._branchLines()) {
            if (this._barcodeId(line[fieldName]) === locationId) {
                continue;
            }
            const alreadyDirty = Boolean(line.dirty);
            this._setBarcodeMany2one(line, fieldName, locationId, locationName);
            const virtualLine = !line.id || String(line.id).startsWith("virtual");
            if (alreadyDirty || virtualLine || line === this.selectedLine) {
                this._markBranchLineDirty(line);
            }
        }
    },

    async _applyBranchLocationOverride(barcodeData, forcedRole) {
        const location = this._branchScannedLocation(barcodeData);
        if (!location || !this.record?.id) {
            return null;
        }
        if (!barcodeData.location || typeof barcodeData.location !== "object") {
            barcodeData.location = location;
        }
        const role = this._branchScanRole(location, forcedRole);
        try {
            const result = await this._branchOrmCall("apply_branch_barcode_location", [
                [this.record.id],
                location.id,
                role,
            ]);
            if (!result?.applied) {
                return null;
            }
            return result;
        } catch (error) {
            this._notifyBranchError(this._rpcErrorMessage(error));
            return false;
        }
    },

    async _runBranchLocationOverride(barcodeData, forcedRole) {
        if (!this._branchLocationOverrideEnabled() || !this.record?.id) {
            return null;
        }
        const location = this._branchScannedLocation(barcodeData);
        if (!location) {
            return null;
        }
        const result = await this._applyBranchLocationOverride(barcodeData, forcedRole);
        if (result === false) {
            barcodeData.stopped = true;
            this.trigger?.("update");
            return false;
        }
        if (!result) {
            return null;
        }
        this._syncBranchLocations(result, barcodeData);
        this._branchPendingRole = result.role;
        return result;
    },

    async _finishBranchLocationOverride(barcodeData, result) {
        if (!result) {
            return;
        }
        this._assignBranchLocation(result, barcodeData);
        this._branchPendingRole = null;
        if (barcodeData.stopped) {
            barcodeData.stopped = false;
            this.trigger?.("playSound", "success");
        }
        this.trigger?.("update");
    },

    async _processLocation(barcodeData) {
        const result = await this._runBranchLocationOverride(barcodeData);
        if (result === false) {
            return;
        }
        const restoreNotifications = result ? this._suppressBranchLocationWarnings() : () => {};
        try {
            await super._processLocation(...arguments);
        } catch (error) {
            if (result) {
                barcodeData.stopped = true;
            } else {
                throw error;
            }
        } finally {
            restoreNotifications();
            this._branchPendingRole = null;
        }
        await this._finishBranchLocationOverride(barcodeData, result);
    },

    async _processLocationSource(barcodeData) {
        if (
            this._branchPendingRole === "dest" &&
            typeof super._processLocationDestination === "function"
        ) {
            return super._processLocationDestination(...arguments);
        }
        const result = this._branchPendingRole
            ? null
            : await this._runBranchLocationOverride(barcodeData, "source");
        if (result === false) {
            return;
        }
        const restoreNotifications = result ? this._suppressBranchLocationWarnings() : () => {};
        try {
            if (typeof super._processLocationSource === "function") {
                await super._processLocationSource(...arguments);
            }
        } catch (error) {
            if (result) {
                barcodeData.stopped = true;
            } else {
                throw error;
            }
        } finally {
            restoreNotifications();
        }
        await this._finishBranchLocationOverride(barcodeData, result);
    },

    async _processLocationDestination(barcodeData) {
        const result = this._branchPendingRole
            ? null
            : await this._runBranchLocationOverride(barcodeData, "dest");
        if (result === false) {
            return;
        }
        const restoreNotifications = result ? this._suppressBranchLocationWarnings() : () => {};
        try {
            if (typeof super._processLocationDestination === "function") {
                await super._processLocationDestination(...arguments);
            }
        } catch (error) {
            if (result) {
                barcodeData.stopped = true;
            } else {
                throw error;
            }
        } finally {
            restoreNotifications();
        }
        await this._finishBranchLocationOverride(barcodeData, result);
    },
});
