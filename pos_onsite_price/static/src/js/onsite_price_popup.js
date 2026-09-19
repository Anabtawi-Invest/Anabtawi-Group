/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
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

    setup() {
        this.state = useState({ selected: null });
    }

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
        return this._tr("Service Type", "نوع الخدمة");
    }

    get popupSubtitle() {
        return this._tr(
            "Choose one option for this order.",
            "اختر خياراً واحداً لهذا الطلب."
        );
    }

    get onSiteLabel() {
        return this._tr("Site Service", "خدمة موقع");
    }

    get cuttingLabel() {
        return this._tr("Cutting Service", "خدمة تقطيع");
    }

    get pledgeLabel() {
        return this._tr("Pledge", "رهن");
    }

    get confirmLabel() {
        return this._tr("Confirm", "تأكيد");
    }

    get cancelLabel() {
        return this._tr("Cancel", "إلغاء");
    }

    select(serviceType) {
        this.state.selected = serviceType;
    }

    confirm() {
        if (!this.state.selected) {
            return;
        }
        this.props.getPayload({ serviceType: this.state.selected });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
