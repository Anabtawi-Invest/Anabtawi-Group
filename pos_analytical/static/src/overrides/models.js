import {patch} from "@web/core/utils/patch";
import {PosOrder} from "@point_of_sale/app/models/pos_order";
import {PosPayment} from "@point_of_sale/app/models/pos_payment";

patch(PosOrder.prototype,{
    setup(_defaultObj, options){
        super.setup(...arguments);
        const account = this.config?.sh_analytic_account;
        if (!account) {
            return;
        }
        this.update(
            {sh_pos_order_analytic_account: account},
            {omitUnknownField: true}
        );
    },
});

patch(PosPayment.prototype,{
    setup(){
        super.setup(...arguments);
        const account = this.models?.["pos.config"]?.getFirst?.()?.sh_analytic_account;
        if (!account) {
            return;
        }
        this.update({sh_analytic_account: account}, {omitUnknownField: true});
    },
});
