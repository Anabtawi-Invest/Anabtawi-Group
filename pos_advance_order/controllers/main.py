from odoo import _, fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.tools import float_compare, float_is_zero
import logging

_logger = logging.getLogger(__name__)


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

    def _ensure_pos_user(self):
        user = request.env.user
        if user.has_group("point_of_sale.group_pos_manager") or user.has_group(
            "point_of_sale.group_pos_user"
        ):
            return user
        raise ValidationError(_("You must be a Point of Sale user to perform this action."))

    @http.route("/pos/advance_order_popup_data", type="jsonrpc", auth="user")
    def advance_order_popup_data(self, company_id=None, **kwargs):
        """Load advance popup lists without model ACL on cashiers."""
        self._ensure_pos_user()
        domain = [("active", "=", True)]
        if company_id:
            domain.append(("company_id", "=", int(company_id)))
        discounts = (
            request.env["pos.advance.discount"]
            .sudo()
            .search_read(
                domain,
                ["id", "name", "discount_type", "value"],
                limit=200,
                order="sequence, id",
            )
        )
        pos_configs = (
            request.env["pos.config"]
            .sudo()
            .search_read(
                [],
                ["id", "name", "pricelist_id", "enable_advance_order"],
                limit=200,
                order="name, id",
            )
        )
        return {"discounts": discounts, "pos_configs": pos_configs}

    @http.route("/pos/create_advance_order", type="jsonrpc", auth="user")
    def create_advance_order(self, data=None, **kwargs):
        """Create POS advance order from Product Screen flow."""
        payload = data if isinstance(data, dict) else kwargs

        partner_id = payload.get("partner_id")
        pos_config_id = payload.get("pos_config_id")
        from_pos_config_id = payload.get("from_pos_config_id")
        lines = payload.get("lines") or []
        advance_amount = float(payload.get("advance_amount") or 0.0)
        amount_tendered = float(payload.get("amount_tendered") or 0.0)
        payment_method_id = payload.get("payment_method_id")
        deposit_pos_session_id = payload.get("deposit_pos_session_id")
        employee_id = payload.get("employee_id")
        discount_id = payload.get("discount_id")
        site_service = bool(payload.get("site_service"))
        _logger.warning(
            "[PLEDGE_CLOSING] create_advance_order request site_service=%s raw=%s partner_id=%s",
            site_service,
            payload.get("site_service"),
            partner_id,
        )

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

        tender_rounding = pos_config.currency_id.rounding or 0.01
        if float_is_zero(amount_tendered, precision_rounding=tender_rounding):
            amount_tendered = advance_amount
        if float_compare(amount_tendered, advance_amount, precision_rounding=tender_rounding) < 0:
            raise ValidationError(
                _("Amount tendered cannot be less than the advance amount.")
            )

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
                        "discount": float(line.get("discount") or 0.0),
                        "tax_ids": [(6, 0, product.taxes_id.ids)],
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

        deposit_session = request.env["pos.session"]
        if deposit_pos_session_id:
            deposit_session = (
                request.env["pos.session"]
                .sudo()
                .browse(int(deposit_pos_session_id))
                .exists()
            )
            if (
                not deposit_session
                or deposit_session.state not in ("opened", "closing_control")
                or deposit_session.rescue
            ):
                deposit_session = request.env["pos.session"]
            elif deposit_session.config_id != from_pos_config:
                # Cashier is on this session; trust the active POS session over the form default.
                from_pos_config = deposit_session.config_id

        if not deposit_session:
            deposit_session = (
                request.env["pos.session"]
                .sudo()
                .search(
                    [
                        ("config_id", "=", from_pos_config.id),
                        ("state", "in", ("opened", "closing_control")),
                        ("rescue", "=", False),
                    ],
                    order="id desc",
                    limit=1,
                )
            )

        company = (
            deposit_session.company_id
            if deposit_session
            else from_pos_config.company_id
        )

        create_vals = {
            "partner_id": partner.id,
            "company_id": company.id,
            "pos_config_id": pos_config.id,
            "from_pos_config_id": from_pos_config.id,
            "picking_date": fields.Datetime.now(),
            "pos_payment_method_id": pm.id,
            "advance_amount": advance_amount,
            "amount_tendered": amount_tendered,
            "line_ids": line_vals,
        }
        if site_service:
            create_vals["site_service"] = True
        if employee_id:
            create_vals["employee_id"] = int(employee_id)
        if discount_id:
            create_vals["discount_id"] = int(discount_id)

        deposit_ctx = {}
        if deposit_session:
            deposit_ctx["pos_advance_deposit_session_id"] = deposit_session.id

        _logger.info(
            "[ADV_TRACE] create_advance_order payload_session=%s resolved_session=%s(%s) "
            "session_state=%s from_pos=%s picking_pos=%s pm=%s amount=%s company=%s ctx=%s",
            deposit_pos_session_id,
            deposit_session.name if deposit_session else False,
            deposit_session.id if deposit_session else False,
            deposit_session.state if deposit_session else False,
            from_pos_config.id,
            pos_config.id,
            pm.id,
            advance_amount,
            company.id,
            deposit_ctx,
        )

        AdvanceOrder = (
            request.env["pos.advance.order"]
            .sudo()
            .with_context(**deposit_ctx, allowed_company_ids=company.ids)
            .with_company(company)
        )
        order = AdvanceOrder.create(create_vals)
        order.with_context(**deposit_ctx).action_confirm()

        if order.advance_amount > 0:
            order.with_context(**deposit_ctx).action_create_payment(
                deposit_pos_session_id=deposit_session.id if deposit_session else None,
            )
            if deposit_session and order.advance_deposit_move_id:
                order._register_deposit_on_pos_session(deposit_session)

        _logger.info(
            "[ADV_TRACE] create_advance_order done advance=%s id=%s state=%s site_service=%s "
            "deposit_move=%s move_ref=%s from_pos=%s company=%s pledge_lines=%s",
            order.name,
            order.id,
            order.state,
            order.site_service,
            order.advance_deposit_move_id.id if order.advance_deposit_move_id else False,
            order.advance_deposit_move_id.ref if order.advance_deposit_move_id else False,
            order.from_pos_config_id.id,
            order.company_id.id,
            order.pledge_line_ids.ids,
        )

        return {
            "id": order.id,
            "name": order.name,
            "state": order.state,
            "amount_total": order.amount_total,
            "pledge_amount": order.pledge_amount,
            "advance_amount": order.advance_amount,
            "amount_tendered": order.amount_tendered,
            "change_amount": order.change_amount,
            "amount_remaining": order.amount_remaining,
            "advance_pos_order_id": order.advance_pos_order_id.id,
        }