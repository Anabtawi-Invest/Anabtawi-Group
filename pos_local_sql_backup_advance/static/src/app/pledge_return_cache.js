/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

const PLEDGE_FIELDS = [
    "id",
    "order_id",
    "pos_order_id",
    "partner_id",
    "employee_id",
    "product_id",
    "pledge_qty",
    "pledge_amount_unit",
    "pledge_subtotal",
    "create_date",
    "state",
    "return_date",
];

export function activePledgeCacheKey(pos) {
    return `pos_pledge_return_cache_${odoo.info?.db || ""}_${pos?.config?.id || 0}`;
}

export function readActivePledgeCache(pos) {
    try {
        const raw = localStorage.getItem(activePledgeCacheKey(pos));
        const data = JSON.parse(raw || "{}");
        return Array.isArray(data.pledges) ? data.pledges : [];
    } catch {
        return [];
    }
}

export function writeActivePledgeCache(pos, pledges) {
    try {
        localStorage.setItem(
            activePledgeCacheKey(pos),
            JSON.stringify({
                pledges: pledges || [],
                saved_at: new Date().toISOString(),
            })
        );
    } catch (error) {
        console.warn("[LOCAL_BACKUP] Could not save active pledges:", error);
    }
}

export function removeActivePledgesFromCache(pos, pledgeIds) {
    const wanted = new Set(pledgeIds || []);
    const pledges = readActivePledgeCache(pos).filter((pledge) => !wanted.has(pledge.id));
    writeActivePledgeCache(pos, pledges);
}

patch(PosStore.prototype, {
    async afterProcessServerData() {
        const result = await super.afterProcessServerData(...arguments);
        this.refreshActivePledgeCache();
        return result;
    },

    async refreshActivePledgeCache() {
        const orm = this.data?.orm;
        if (!orm || !this.config?.id) {
            return;
        }
        try {
            const rows = await orm.searchRead(
                "pos.advance.order.pledge",
                [["state", "=", "active"]],
                PLEDGE_FIELDS,
                { limit: 1000, order: "create_date desc" }
            );
            const employeeIds = [
                ...new Set(
                    (rows || []).map((row) => row.employee_id?.[0]).filter(Boolean)
                ),
            ];
            let employeeNameById = {};
            if (employeeIds.length) {
                const employees = await orm.searchRead(
                    "hr.employee",
                    [["id", "in", employeeIds]],
                    ["id", "name"]
                );
                employeeNameById = (employees || []).reduce((acc, emp) => {
                    acc[emp.id] = emp.name || "";
                    return acc;
                }, {});
            }
            const partnerIds = [
                ...new Set((rows || []).map((row) => row.partner_id?.[0]).filter(Boolean)),
            ];
            let partnerPhoneById = {};
            if (partnerIds.length) {
                const partners = await orm.searchRead(
                    "res.partner",
                    [["id", "in", partnerIds]],
                    ["id", "phone"]
                );
                partnerPhoneById = (partners || []).reduce((acc, partner) => {
                    acc[partner.id] = partner.phone || "";
                    return acc;
                }, {});
            }
            const cached = (rows || []).map((row) => ({
                ...row,
                name: row.order_id?.[1] || row.pos_order_id?.[1] || "POS Pledge",
                pledge_amount: row.pledge_subtotal || 0,
                employee_amount: 0,
                delivery_amount: 0,
                case_type: "case2",
                employee_name: row.employee_id?.[0]
                    ? employeeNameById[row.employee_id[0]] || ""
                    : "",
                partner_phone: row.partner_id?.[0]
                    ? partnerPhoneById[row.partner_id[0]] || ""
                    : "",
                from_server_cache: true,
            }));
            writeActivePledgeCache(this, cached);
            console.info(
                `[LOCAL_BACKUP] Saved ${cached.length} active pledge(s) for offline return.`
            );
        } catch (error) {
            if (readActivePledgeCache(this).length) {
                console.info(
                    "[LOCAL_BACKUP] Could not refresh active pledges; keeping the last saved list."
                );
            } else {
                console.warn("[LOCAL_BACKUP] Active pledges were not saved:", error);
            }
        }
    },
});
