from odoo import _, fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request


class PosAdvanceOrderController(http.Controller):

    def _validate_advance_payment_method(self, pm, from_pos_config):
        if not pm or not pm.exists():
            raise ValidationError(_("Invalid POS payment method."))
        if from_pos_config not in pm.config_ids:
            raise ValidationError(
                _("This payment method is not available on the current Point of Sale.")
            )
        if pm.type == "pay_later":
            raise UserError(_("Customer account payments cannot be used for advance deposits."))
        if pm.payment_method_type and pm.payment_method_type != "none":
            raise UserError(
                _("Integrated POS payment methods (terminal / QR) are not supported for advance deposits.")
            )

    @http.route("/pos/create_advance_order", type="jsonrpc", auth="user")
    def create_advance_order(self, data=None, **kwargs):
        """Create POS advance order from Product Screen flow."""
        payload = data if isinstance(data, dict) else kwargs

        partner_id = payload.get("partner_id")
        pos_config_id = payload.get("pos_config_id")
        from_pos_config_id = payload.get("from_pos_config_id")
        lines = payload.get("lines") or []
        advance_amount = float(payload.get("advance_amount") or 0.0)
        payment_method_id = payload.get("payment_method_id")
        employee_id = payload.get("employee_id")
        discount_id = payload.get("discount_id")

        if not partner_id:
            raise ValidationError("Customer is required.")
        if not pos_config_id:
            raise ValidationError("POS configuration is required.")
        if not lines:
            raise ValidationError("Order lines are required.")
        if advance_amount <= 0:
            raise ValidationError("Advance amount must be greater than zero.")

        pos_config = request.env["pos.config"].sudo().browse(int(pos_config_id)).exists()
        if not pos_config:
            raise ValidationError("Invalid POS configuration.")

        partner = request.env["res.partner"].sudo().browse(int(partner_id)).exists()
        if not partner:
            raise ValidationError("Invalid customer.")

        line_vals = []
        for line in lines:
            product_id = int(line.get("product_id") or 0)
            qty = float(line.get("qty") or 0.0)
            if not product_id or qty <= 0:
                continue

            product = request.env["product.product"].sudo().browse(product_id).exists()
            if not product:
                continue

            line_vals.append(
                (
                    0,
                    0,
                    {
                        "product_id": product.id,
                        "product_qty": qty,
                        "price_unit": float(line.get("price_unit") or product.lst_price or 0.0),
                    },
                )
            )

        if not line_vals:
            raise ValidationError("Order lines are required.")

        from_pos_config = request.env["pos.config"].sudo().browse(
            int(from_pos_config_id or pos_config.id)
        ).exists()
        if not from_pos_config:
            raise ValidationError("Invalid source POS configuration.")
        if not from_pos_config.enable_advance_order:
            raise UserError("Advance order is not enabled on this POS.")

        if not payment_method_id:
            raise ValidationError(_("Please select a payment method."))
        pm = request.env["pos.payment.method"].sudo().browse(int(payment_method_id))
        self._validate_advance_payment_method(pm, from_pos_config)

        create_vals = {
            "partner_id": partner.id,
            "pos_config_id": pos_config.id,
            "from_pos_config_id": from_pos_config.id,
            "picking_date": fields.Datetime.now(),
            "pos_payment_method_id": pm.id,
            "advance_amount": advance_amount,
            "line_ids": line_vals,
        }
        if employee_id:
            create_vals["employee_id"] = int(employee_id)
            create_vals["with_employee"] = True
        if discount_id:
            create_vals["discount_id"] = int(discount_id)

        order = request.env["pos.advance.order"].sudo().create(create_vals)
        order.action_confirm()

        if order.advance_amount > 0:
            order.action_create_payment()

        return {
            "id": order.id,
            "name": order.name,
            "state": order.state,
            "amount_total": order.amount_total,
            "advance_amount": order.advance_amount,
            "advance_pos_order_id": order.advance_pos_order_id.id,
        }