/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { accountTaxHelpers } from "@account/helpers/account_tax";

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(...arguments);
        this.manual_fiscal_position_applied = Boolean(vals.manual_fiscal_position_applied);
    },

    serializeForORM(opts = {}) {
        const data = super.serializeForORM(opts);
        data.manual_fiscal_position_applied = Boolean(this.manual_fiscal_position_applied);
        return data;
    },

    _getSourceTaxesForLine(line) {
        const companyId = this.company_id?.id;
        return (line.product_id?.taxes_id || []).filter(
            (tax) => !tax.company_id || !tax.company_id.id || tax.company_id.id === companyId
        );
    },

    _getMappedTaxes(sourceTaxes, fiscalPosition) {
        if (!fiscalPosition) {
            return sourceTaxes;
        }
        return fiscalPosition.getTaxesAfterFiscalPosition(sourceTaxes);
    },

    _applyFiscalPositionPriceMapping(previousFiscalPosition, newFiscalPosition) {
        const previousId = previousFiscalPosition?.id || false;
        const newId = newFiscalPosition?.id || false;
        if (previousId === newId) {
            return;
        }

        const keepMappedPrice = Boolean(
            newFiscalPosition?.keep_pricelist_price_after_tax_mapping
        );
        for (const line of this.lines) {
            if (!line.product_id || line.price_type === "manual") {
                continue;
            }
            const sourceTaxes = this._getSourceTaxesForLine(line);
            const previousMappedTaxes = this._getMappedTaxes(sourceTaxes, previousFiscalPosition);
            const newMappedTaxes = this._getMappedTaxes(sourceTaxes, newFiscalPosition);
            if (keepMappedPrice) {
                continue;
            }
            const newUnitPrice = accountTaxHelpers.adapt_price_unit_to_another_taxes(
                line.price_unit,
                line.product_id,
                previousMappedTaxes,
                newMappedTaxes
            );
            line.setUnitPrice(newUnitPrice);
        }
        this.triggerRecomputeAllPrices();
    },

    setFiscalPosition(fiscalPosition, { manual = false } = {}) {
        this.assertEditable();
        const previousFiscalPosition = this.fiscal_position_id || false;
        this.fiscal_position_id = fiscalPosition || false;
        this.manual_fiscal_position_applied = Boolean(manual && this.fiscal_position_id);
        this._applyFiscalPositionPriceMapping(previousFiscalPosition, this.fiscal_position_id);
    },

    updatePricelistAndFiscalPosition(newPartner) {
        const previousFiscalPosition = this.fiscal_position_id || false;
        super.updatePricelistAndFiscalPosition(...arguments);
        this.manual_fiscal_position_applied = false;
        this._applyFiscalPositionPriceMapping(previousFiscalPosition, this.fiscal_position_id);
    },
});

patch(ControlButtons.prototype, {
    async clickFiscalPosition() {
        const partner = this.currentOrder?.getPartner();
        if (!partner || !partner.id) {
            this.notification.add(_t("Select a customer first before changing Fiscal Position."), {
                type: "warning",
            });
            return;
        }

        const currentFiscalPosition = this.currentOrder.fiscal_position_id;
        const fiscalPosList = [
            {
                id: -1,
                label: this.pos.config.module_pos_restaurant ? _t("Dine in") : _t("Original Tax"),
                isSelected: false,
                item: "none",
            },
        ];
        for (const fiscalPos of this.pos.config.fiscal_position_ids) {
            fiscalPosList.push({
                id: fiscalPos.id,
                label: fiscalPos.name,
                isSelected: currentFiscalPosition
                    ? fiscalPos.id === currentFiscalPosition.id
                    : false,
                item: fiscalPos,
            });
        }

        const selectedFiscalPosition = await makeAwaitable(this.dialog, SelectionPopup, {
            list: fiscalPosList,
            title: _t("Choose the tax you want to apply"),
        });

        if (!selectedFiscalPosition) {
            return;
        }

        if (selectedFiscalPosition === "none") {
            this.currentOrder.setFiscalPosition(false, { manual: true });
            return;
        }

        this.currentOrder.setFiscalPosition(selectedFiscalPosition || false, { manual: true });
    },
});
