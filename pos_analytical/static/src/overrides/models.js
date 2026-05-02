/** @odoo-module **/

import {patch} from "@web/core/utils/patch";
import {PosOrder} from "@point_of_sale/app/models/pos_order";
import {PosPayment} from "@point_of_sale/app/models/pos_payment";

patch(PosOrder.prototype,{
    setup(_defaultObj,options){
        super.setup(...arguments);
        this.update({sh_pos_order_analytic_account : this.config.sh_analytic_account})
    },

});

patch(PosPayment.prototype,{
    setup(){
        super.setup(...arguments);
        console.log("POs is here");
        this.sh_analytic_account = this.models["pos.config"].getFirst().sh_analytic_account
        this.update({sh_analytic_account : this.sh_analytic_account})
    }
})
