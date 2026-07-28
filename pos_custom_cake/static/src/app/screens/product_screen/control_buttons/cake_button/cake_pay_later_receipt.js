/** @odoo-module **/

import { Component } from "@odoo/owl";

export class CakePayLaterReceipt extends Component {
    static template = "pos_custom_cake.CakePayLaterReceipt";
    static props = {
        receipt: Object,
    };
}
