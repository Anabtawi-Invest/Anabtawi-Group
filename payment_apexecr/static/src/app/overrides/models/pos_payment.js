import { PosPayment } from "@point_of_sale/app/models/pos_payment";
import { patch } from "@web/core/utils/patch";

patch(PosPayment.prototype, {
    setup(vals) {
        super.setup(vals);
        this.uiState = {
            ...(this.uiState ?? {}),
            apexecr_parent_rrn: null,
            apexecr_parent_auth_code: null,
        };
    },
    updateRefundPaymentLine(refundedPaymentLine) {
        super.updateRefundPaymentLine(refundedPaymentLine);
        this.uiState.apexecr_parent_rrn = refundedPaymentLine?.apexecr_rrn || null;
        this.uiState.apexecr_parent_auth_code = refundedPaymentLine?.apexecr_auth_code || null;
    },
});

