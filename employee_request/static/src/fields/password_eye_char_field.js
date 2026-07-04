/** @odoo-module **/

import { registry } from "@web/core/registry";
import { exprToBoolean } from "@web/core/utils/strings";
import { formatChar } from "@web/views/fields/formatters";
import { useInputField } from "@web/views/fields/input_field_hook";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

import { Component, useRef, useState } from "@odoo/owl";

export class PasswordEyeCharField extends Component {
    static template = "employee_request.PasswordEyeCharField";
    static props = {
        ...standardFieldProps,
        isPassword: { type: Boolean, optional: true },
        placeholder: { type: String, optional: true },
        autocomplete: { type: String, optional: true },
    };

    setup() {
        this.input = useRef("input");
        this.state = useState({ show: false });
        useInputField({
            getValue: () => this.props.record.data[this.props.name] || "",
            parse: (v) => v,
        });
    }

    get value() {
        return this.props.record.data[this.props.name] || "";
    }

    get maskedValue() {
        return formatChar(this.value, { isPassword: true });
    }

    toggleShow() {
        this.state.show = !this.state.show;
    }
}

export const passwordEyeCharField = {
    component: PasswordEyeCharField,
    supportedTypes: ["char", "text"],
    extractProps: ({ attrs, placeholder }) => ({
        isPassword: exprToBoolean(attrs.password),
        placeholder,
        autocomplete: attrs.autocomplete,
    }),
};

registry.category("fields").add("password_eye_char", passwordEyeCharField);

