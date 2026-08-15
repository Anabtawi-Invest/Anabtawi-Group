/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";

function recordFlag(record, name) {
    if (!record) {
        return undefined;
    }
    if (record[name] !== undefined) {
        return record[name];
    }
    if (record.raw && record.raw[name] !== undefined) {
        return record.raw[name];
    }
    return undefined;
}

patch(PosStore.prototype, {
    _getPosCashier() {
        return this.getCashier?.() || this.get_cashier?.() || this.user;
    },

    isCashierRestrictedFromQtyChange() {
        const cashier = this._getPosCashier();
        const cashierFlag = recordFlag(cashier, "_restrict_pos_qty_change");
        if (cashierFlag !== undefined) {
            return Boolean(cashierFlag);
        }
        return Boolean(this.config?._restrict_pos_qty_change);
    },

    isReturnOrder(order = this.getOrder()) {
        return Boolean(
            order?.isRefund ||
                order?.is_refund ||
                order?.preset_id?.is_return ||
                order?.isRefundInProcess?.()
        );
    },

    isProductQtyRestricted(product) {
        if (!product) {
            return false;
        }
        const template = product.product_tmpl_id || product;
        return Boolean(product.pos_allowed_change_qty || template.pos_allowed_change_qty);
    },

    isPosQtyChangeRestricted(line, order = this.getOrder()) {
        if (!this.isCashierRestrictedFromQtyChange()) {
            return false;
        }
        if (this.isReturnOrder(order)) {
            return false;
        }
        if (line?.refunded_orderline_id) {
            return false;
        }
        const product = line?.product_id || line;
        return this.isProductQtyRestricted(product);
    },

    showPosQtyChangeDenied() {
        this.dialog.add(AlertDialog, {
            title: _t("Access Denied"),
            body: _t("You are not allowed to change the quantity of this product."),
        });
    },

    tryMergeOrderline(order, line, merge, selectedOrderline) {
        if (merge !== false && this.isPosQtyChangeRestricted(line, order)) {
            for (const curLine of order.lines) {
                if (curLine.id !== line.id && curLine.canBeMergedWith(line)) {
                    this.showPosQtyChangeDenied();
                    line.delete();
                    this.selectOrderLine(order, curLine);
                    return;
                }
            }
        }
        return super.tryMergeOrderline(order, line, merge, selectedOrderline);
    },
});
