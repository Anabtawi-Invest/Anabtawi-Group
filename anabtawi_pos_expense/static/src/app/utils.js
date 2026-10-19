import { _t } from "@web/core/l10n/translation";
import { formatDateTime } from "@web/core/l10n/dates";
import { CashMoveReceipt } from "@point_of_sale/app/components/popups/cash_move_popup/cash_move_receipt/cash_move_receipt";

const { DateTime } = luxon;

export function getPosExpenseCashierArgs(pos) {
    const cashier = pos.getCashier?.();
    const employeeId = pos.config.module_pos_hr ? cashier?.id : false;
    return [cashier?.name || false, employeeId || false];
}

export async function printPosExpenseReceipt(pos, printer, { reason, formattedAmount, type }) {
    const order = pos.models["pos.order"].create({
        session_id: pos.session,
        company_id: pos.company,
        config_id: pos.config,
        user_id: pos.user,
        ticket_code: "",
        tracking_number: "",
        sequence_number: 0,
        pos_reference: "",
        state: "cancel",
    });
    try {
        await printer.print(CashMoveReceipt, {
            reason,
            translatedType: type === "in" ? _t("in") : _t("out"),
            order,
            formattedAmount,
            date: formatDateTime(DateTime.now()),
        });
    } catch {
        // The cash move is already saved; a printer problem must not block the cashier.
    } finally {
        pos.models["pos.order"].delete(order);
    }
}
