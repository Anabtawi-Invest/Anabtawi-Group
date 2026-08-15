/** @odoo-module **/

import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

export class OnSitePricePopup extends Component {
    static template = "pos_onsite_price.OnSitePricePopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: Function,
        pos: { type: Object, optional: true },
    };

    _isArabicContext() {
        const urlLang = new URLSearchParams(window.location.search).get("lang") || "";
        const htmlLang = document?.documentElement?.lang || "";
        const bodyDir = document?.body ? window.getComputedStyle(document.body).direction : "";
        return urlLang.startsWith("ar") || htmlLang.startsWith("ar") || bodyDir === "rtl";
    }

    _tr(msgid, fallbackArabic) {
        const translated = _t(msgid);
        if (translated === msgid && this._isArabicContext()) {
            return fallbackArabic;
        }
        return translated;
    }

    get popupTitle() {
        return this._tr("On Site Order", "طلب بالموقع");
    }

    get popupSubtitle() {
        return this._tr("Is this order on site?", "هل هذا الطلب بالموقع؟");
    }

    get yesLabel() {
        return this._tr("Yes", "نعم");
    }

    get noLabel() {
        return this._tr("No", "لا");
    }

    get cancelLabel() {
        return this._tr("Cancel", "إلغاء");
    }

    confirm(isOnSite) {
        this.props.getPayload({ isOnSite });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
