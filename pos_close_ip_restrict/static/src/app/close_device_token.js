/** @odoo-module **/

import { uuidv4 } from "@point_of_sale/utils";

const storageKey = () => `${odoo.access_token}-pos-close-device`;

export function getCloseDeviceToken() {
    return localStorage.getItem(storageKey()) || "";
}

export function getOrCreateCloseDeviceToken() {
    let token = getCloseDeviceToken();
    if (!token) {
        token = uuidv4();
        localStorage.setItem(storageKey(), token);
    }
    return token;
}

export function closeDeviceContext(extra = {}) {
    const token = getCloseDeviceToken();
    return {
        ...extra,
        close_device_token: token || false,
    };
}
