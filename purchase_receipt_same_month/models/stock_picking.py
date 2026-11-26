from odoo import _, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):
        self._check_purchase_receipt_same_month()
        return super().button_validate()

    def _check_purchase_receipt_same_month(self):
        for picking in self:
            if picking.picking_type_code != "incoming":
                continue
            if not picking.company_id.purchase_receipt_same_month:
                continue
            orders = picking.move_ids.filtered(
                lambda move: move.state != "cancel"
            ).sudo().purchase_line_id.order_id
            if not orders:
                continue
            receipt_date = picking._purchase_receipt_validation_date()
            mismatches = []
            for order in orders:
                if order.allow_receipt_other_month:
                    continue
                po_date = picking._purchase_order_month_date(order)
                if not po_date:
                    continue
                if (po_date.year, po_date.month) != (receipt_date.year, receipt_date.month):
                    mismatches.append((order, po_date))
            if mismatches:
                picking._raise_purchase_receipt_month_error(receipt_date, mismatches)

    def _purchase_receipt_validation_date(self):
        self.ensure_one()
        moment = self.date_done or fields.Datetime.now()
        return fields.Datetime.context_timestamp(self, moment).date()

    def _purchase_order_month_date(self, order):
        moment = order.date_approve or order.date_order
        if not moment:
            return False
        return fields.Datetime.context_timestamp(self, moment).date()

    def _raise_purchase_receipt_month_error(self, receipt_date, mismatches):
        self.ensure_one()
        order_lines = "\n".join(
            _(
                "- %(po)s is in %(month)s",
                po=order.display_name,
                month=po_date.strftime("%B %Y"),
            )
            for order, po_date in mismatches
        )
        raise UserError(_(
            "You cannot validate receipt %(receipt)s.\n\n"
            "The purchase order month is not the same month as this receipt (%(receipt_month)s).\n"
            "%(orders)s\n\n"
            "Create a new purchase order for this month.",
            receipt=self.display_name,
            receipt_month=receipt_date.strftime("%B %Y"),
            orders=order_lines,
        ))
