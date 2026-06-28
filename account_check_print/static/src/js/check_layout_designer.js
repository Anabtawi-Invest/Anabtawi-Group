/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class CheckLayoutDesigner extends Component {
    static template = "account_check_print.CheckLayoutDesigner";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.actionService = useService("action");
        this.canvasRef = useRef("canvas");
        this.layoutId = this.props.action.params.layout_id;
        this.state = useState({
            loading: true,
            saving: false,
            name: "",
            paperWidth: 1,
            paperHeight: 1,
            fontSize: 11,
            backgroundUrl: false,
            fields: {},
            selected: "payee",
            showGuides: true,
        });
        this.pointerCleanup = null;
        onWillStart(() => this.loadLayout());
        onWillUnmount(() => this.stopPointerTracking());
    }

    async loadLayout() {
        const data = await this.orm.call(
            "account.check.layout",
            "get_designer_data",
            [[this.layoutId]]
        );
        this.state.name = data.name;
        this.state.paperWidth = data.paper_width;
        this.state.paperHeight = data.paper_height;
        this.state.fontSize = data.font_size;
        this.state.backgroundUrl = data.background_url;
        this.state.fields = data.fields;
        this.state.loading = false;
    }

    get fieldEntries() {
        const labels = {
            date: "Date",
            payee: "Payee",
            amount: "Numeric Amount",
            amount_words: "Amount in Words",
            memo: "Memo",
            signature: "Signature",
            logo: "Logo",
            check_number: "Check Number",
        };
        const samples = {
            date: "28/06/2026",
            payee: "Sample Vendor",
            amount: "1,250.000",
            amount_words: "One Thousand Two Hundred Fifty",
            memo: "Invoice reference",
            signature: "Signature",
            logo: "Company Logo",
            check_number: "000001",
        };
        return Object.entries(this.state.fields).map(([name, geometry]) => ({
            name,
            label: labels[name],
            sample: samples[name],
            geometry,
        }));
    }

    canvasStyle() {
        return `aspect-ratio:${this.state.paperWidth}/${this.state.paperHeight};`;
    }

    fieldStyle(field) {
        const g = field.geometry;
        return [
            `left:${(g.x / this.state.paperWidth) * 100}%`,
            `top:${(g.y / this.state.paperHeight) * 100}%`,
            `width:${(g.width / this.state.paperWidth) * 100}%`,
            `height:${(g.height / this.state.paperHeight) * 100}%`,
            `font-size:${this.state.fontSize}pt`,
        ].join(";");
    }

    selectField(name) {
        this.state.selected = name;
    }

    startPointerTracking(ev, name, mode) {
        ev.preventDefault();
        ev.stopPropagation();
        this.selectField(name);
        this.stopPointerTracking();
        const canvas = this.canvasRef.el;
        const geometry = this.state.fields[name];
        const start = {
            clientX: ev.clientX,
            clientY: ev.clientY,
            x: geometry.x,
            y: geometry.y,
            width: geometry.width,
            height: geometry.height,
        };
        const xScale = this.state.paperWidth / canvas.clientWidth;
        const yScale = this.state.paperHeight / canvas.clientHeight;
        const move = (moveEv) => {
            const dx = (moveEv.clientX - start.clientX) * xScale;
            const dy = (moveEv.clientY - start.clientY) * yScale;
            if (mode === "move") {
                geometry.x = this.clamp(start.x + dx, 0, this.state.paperWidth - geometry.width);
                geometry.y = this.clamp(start.y + dy, 0, this.state.paperHeight - geometry.height);
            } else {
                geometry.width = this.clamp(start.width + dx, 2, this.state.paperWidth - geometry.x);
                geometry.height = this.clamp(start.height + dy, 2, this.state.paperHeight - geometry.y);
            }
        };
        const stop = () => this.stopPointerTracking();
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", stop, { once: true });
        this.pointerCleanup = () => {
            window.removeEventListener("pointermove", move);
            window.removeEventListener("pointerup", stop);
        };
    }

    stopPointerTracking() {
        if (this.pointerCleanup) {
            this.pointerCleanup();
            this.pointerCleanup = null;
        }
    }

    clamp(value, minimum, maximum) {
        return Math.min(Math.max(value, minimum), Math.max(minimum, maximum));
    }

    updateGeometry(name, key, ev) {
        const value = Number(ev.target.value);
        if (!Number.isFinite(value)) {
            return;
        }
        const geometry = this.state.fields[name];
        const maximum = key === "x" || key === "width" ? this.state.paperWidth : this.state.paperHeight;
        geometry[key] = this.clamp(value, 0, maximum);
    }

    async save() {
        this.state.saving = true;
        try {
            await this.orm.call(
                "account.check.layout",
                "save_designer_data",
                [[this.layoutId], this.state.fields]
            );
            this.notification.add("Check layout saved.", { type: "success" });
        } finally {
            this.state.saving = false;
        }
    }

    async uploadBackground(ev) {
        const file = ev.target.files[0];
        if (!file) {
            return;
        }
        if (!file.type.startsWith("image/")) {
            this.notification.add("Select an image file.", { type: "warning" });
            return;
        }
        const dataUrl = await this.readFile(file);
        const content = dataUrl.split(",", 2)[1];
        await this.orm.write("account.check.layout", [this.layoutId], {
            background_image: content,
            background_filename: file.name,
        });
        this.state.backgroundUrl = `${dataUrl}`;
        this.notification.add("Background image uploaded.", { type: "success" });
        ev.target.value = "";
    }

    readFile(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = () => reject(reader.error);
            reader.readAsDataURL(file);
        });
    }

    toggleGuides() {
        this.state.showGuides = !this.state.showGuides;
    }

    close() {
        this.actionService.doAction({ type: "ir.actions.act_window_close" });
    }
}

registry.category("actions").add("account_check_print.layout_designer", CheckLayoutDesigner);

