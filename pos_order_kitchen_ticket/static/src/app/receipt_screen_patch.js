/** @odoo-module **/

import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { OrderKitchenTicket } from "./order_kitchen_ticket";

ReceiptScreen.components = { ...ReceiptScreen.components, OrderKitchenTicket };
