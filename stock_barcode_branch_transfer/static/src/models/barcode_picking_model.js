import BarcodePickingModel from "@stock_barcode/models/barcode_picking_model";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

patch(BarcodePickingModel.prototype, {
    _branchLocationOverrideEnabled() {
        return Boolean(this.config?.barcode_override_scanned_locations);
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

    _branchSourceLockedId() {
        return this._barcodeId(this.record?.barcode_locked_source_location_id);
    },

    _branchDestLockedId() {
        if (!this.record?.barcode_dest_locked_by_scan) {
            return false;
        }
        return this._barcodeId(this.record?.barcode_locked_dest_location_id);
    },

    _branchLocationsReady() {
        return Boolean(this._branchSourceLockedId() && this._branchDestLockedId());
    },

    /**
     * Default Stock on the transfer is not a scanned lock. Clear it so the
     * barcode screen asks for source, then destination, then products.
     */
    _branchSyncScanPrompts() {
        if (!this._branchLocationOverrideEnabled() || !this.lastScanned) {
            return;
        }
        const sourceId = this._branchSourceLockedId();
        const destId = this._branchDestLockedId();
        if (!sourceId) {
            this.lastScanned.sourceLocation = false;
            this.lastScanned.destLocation = false;
            return;
        }
        if (!this.lastScanned.sourceLocation || this._barcodeId(this.lastScanned.sourceLocation) !== sourceId) {
            this.lastScanned.sourceLocation = this._cacheLocation(sourceId) || this.lastScanned.sourceLocation;
        }
        if (!destId) {
            this.lastScanned.destLocation = false;
            return;
        }
        if (!this.lastScanned.destLocation || this._barcodeId(this.lastScanned.destLocation) !== destId) {
            this.lastScanned.destLocation = this._cacheLocation(destId) || this.lastScanned.destLocation;
        }
    },

    _cacheLocation(id) {
        if (!id || typeof this.cache?.getRecord !== "function") {
            return null;
        }
        try {
            return this.cache.getRecord("stock.location", id, false);
        } catch {
            return null;
        }
    },

    /**
     * Picking records store a location id. Line records store the full
     * location, including parent_path, which the barcode line template reads.
     */
    _setBarcodeMany2one(record, fieldName, id, name, scannedLocation) {
        if (!record) {
            return;
        }
        const current = record[fieldName];
        if (!current || typeof current !== "object" || Array.isArray(current)) {
            record[fieldName] = id || false;
            return;
        }
        const scanned = scannedLocation && this._barcodeId(scannedLocation) === id
            ? scannedLocation
            : null;
        const cached = scanned?.parent_path ? scanned : this._cacheLocation(id);
        const next = cached ? { ...cached } : { ...current, id: id || false };
        next.id = id || false;
        next.display_name = cached?.display_name || name || current.display_name || "";
        if (typeof next.parent_path !== "string") {
            next.parent_path = current.id === id && typeof current.parent_path === "string"
                ? current.parent_path
                : "";
        }
        record[fieldName] = next;
    },

    _isSublocation(childLocation, parentLocation) {
        const childPath = childLocation?.parent_path;
        const parentPath = parentLocation?.parent_path;
        if (typeof childPath !== "string" || typeof parentPath !== "string") {
            return false;
        }
        return super._isSublocation(childLocation, parentLocation);
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

    _branchScanRole(location, forcedRole) {
        if (forcedRole === "source" || forcedRole === "dest") {
            return forcedRole;
        }
        const lockedSourceId = this._branchSourceLockedId();
        const lockedDestId = this._branchDestLockedId();
        if (!lockedSourceId) {
            return "source";
        }
        if (location.id === lockedSourceId && location.id !== lockedDestId) {
            return "source";
        }
        if (!lockedDestId) {
            return "dest";
        }
        if (location.id === lockedDestId) {
            return "dest";
        }
        return "dest";
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
            const scanned = barcodeData?.location;
            this._setBarcodeMany2one(
                record,
                "location_id",
                result.location_id,
                result.location_name,
                scanned
            );
            this._setBarcodeMany2one(
                record,
                "location_dest_id",
                result.location_dest_id,
                result.location_dest_name,
                scanned
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
            if (result.role === "dest") {
                record.barcode_dest_locked_by_scan = true;
            }
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
                this.lastScanned.destLocation = false;
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
            this._setBarcodeMany2one(line, fieldName, locationId, locationName, location);
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
        // A location barcode must not continue into the product path.
        barcodeData.stopped = true;
        this.trigger?.("update");
    },

    async _processBranchLocationByRole(barcodeData, result) {
        const role = result?.role || this._branchPendingRole;
        const restoreNotifications = result ? this._suppressBranchLocationWarnings() : () => {};
        try {
            if (role === "dest" && typeof super._processLocationDestination === "function") {
                if (!barcodeData.destLocation) {
                    barcodeData.destLocation = barcodeData.location;
                }
                await super._processLocationDestination(barcodeData);
            } else if (typeof super._processLocationSource === "function") {
                await super._processLocationSource(barcodeData);
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

    _getDefaultMessageType() {
        this._branchSyncScanPrompts();
        if (this._branchLocationOverrideEnabled()) {
            if (!this._branchSourceLockedId()) {
                return "scan_src";
            }
            if (!this._branchDestLockedId()) {
                return "scan_dest";
            }
        }
        return super._getDefaultMessageType(...arguments);
    },

    get barcodeInfo() {
        this._branchSyncScanPrompts();
        const info = super.barcodeInfo;
        if (!this._branchLocationOverrideEnabled() || !info) {
            return info;
        }
        if (!this._branchSourceLockedId()) {
            return {
                ...info,
                class: "scan_src",
                icon: "sign-out",
                message: _t("Scan the source location"),
            };
        }
        if (!this._branchDestLockedId()) {
            return {
                ...info,
                class: "scan_dest",
                icon: "sign-in",
                message: _t("Scan the destination location"),
            };
        }
        return info;
    },

    _checkBarcode(barcodeData) {
        this._branchSyncScanPrompts();
        if (this._branchLocationOverrideEnabled()) {
            const location = this._branchScannedLocation(barcodeData);
            const hasProductOrPackage = Boolean(
                barcodeData?.product
                || barcodeData?.package
                || barcodeData?.packaging
                || barcodeData?.lot
                || barcodeData?.lotName
            );
            if (!this._branchSourceLockedId()) {
                if (!location && hasProductOrPackage) {
                    return {
                        title: _t("Source location required"),
                        message: _t("Scan the source location before scanning products."),
                        error: true,
                    };
                }
            } else if (!this._branchDestLockedId()) {
                if (!location && hasProductOrPackage) {
                    return {
                        title: _t("Destination location required"),
                        message: _t("Scan the destination location before scanning products."),
                        error: true,
                    };
                }
            }
        }
        return super._checkBarcode(...arguments);
    },

    _setLocationFromBarcode(result, location) {
        if (this._branchLocationOverrideEnabled()) {
            if (!this._branchSourceLockedId()) {
                result.location = location;
                return result;
            }
            if (!this._branchDestLockedId()) {
                result.destLocation = location;
                result.location = location;
                return result;
            }
        }
        return super._setLocationFromBarcode(...arguments);
    },

    async _processLocation(barcodeData) {
        if (!this._branchLocationOverrideEnabled()) {
            return super._processLocation(...arguments);
        }
        const result = await this._runBranchLocationOverride(barcodeData);
        if (result === false) {
            return;
        }
        if (!result) {
            return super._processLocation(...arguments);
        }
        await this._processBranchLocationByRole(barcodeData, result);
    },

    async _processLocationSource(barcodeData) {
        if (!this._branchLocationOverrideEnabled()) {
            return super._processLocationSource(...arguments);
        }
        if (
            this._branchPendingRole === "dest"
            && typeof super._processLocationDestination === "function"
        ) {
            return super._processLocationDestination(...arguments);
        }
        const result = this._branchPendingRole
            ? null
            : await this._runBranchLocationOverride(barcodeData);
        if (result === false) {
            return;
        }
        if (result) {
            await this._processBranchLocationByRole(barcodeData, result);
            return;
        }
        if (typeof super._processLocationSource === "function") {
            return super._processLocationSource(...arguments);
        }
    },

    async _processLocationDestination(barcodeData) {
        if (!this._branchLocationOverrideEnabled()) {
            return super._processLocationDestination(...arguments);
        }
        const result = this._branchPendingRole
            ? null
            : await this._runBranchLocationOverride(barcodeData, "dest");
        if (result === false) {
            return;
        }
        if (result) {
            await this._processBranchLocationByRole(barcodeData, result);
            return;
        }
        if (typeof super._processLocationDestination === "function") {
            return super._processLocationDestination(...arguments);
        }
    },
});
