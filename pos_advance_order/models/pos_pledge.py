# -*- coding: utf-8 -*-

import logging
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class PosAdvanceOrderPledge(models.Model):
    _name = "pos.advance.order.pledge"
    _description = "POS Advance Order Pledge"
    _order = "id desc"

    # Advance order pledges OR POS pledges (pos_pledge frontend flow)
    order_id = fields.Many2one(
        "pos.advance.order",
        string="Advance Order",
        required=False,
        ondelete="cascade",
    )
    pos_order_id = fields.Many2one("pos.order", string="Order", ondelete="cascade", index=True)
    partner_id = fields.Many2one("res.partner", string="Customer", index=True)
    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        compute="_compute_employee_id",
        store=True,
        readonly=True,
        help="Filled from the linked advance order or POS order employee when set.",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Pledge Product",
        required=True,
        domain=[("available_in_pos", "=", True)],
    )
    source_product_id = fields.Many2one(
        "product.product",
        string="Source Menu Product",
        help="Site Service menu product that triggered this pledge line.",
    )
    advance_line_id = fields.Many2one(
        "pos.advance.order.line",
        string="Advance Line",
        ondelete="cascade",
        index=True,
    )
    pledge_qty = fields.Float(string="Pledge Qty", default=1.0)
    pledge_amount_unit = fields.Monetary(
        string="Pledge Unit Amount",
        currency_field="currency_id",
        default=0.0,
    )
    currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_currency_id",
        store=True,
        readonly=True,
    )
    pledge_subtotal = fields.Monetary(
        string="Pledge Total",
        currency_field="currency_id",
        compute="_compute_pledge_subtotal",
        store=True,
        readonly=True,
    )
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("active", "Active"),
            ("returned", "Returned"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="pending",
        index=True,
    )
    receive_date = fields.Datetime(
        string="Received On",
        readonly=True,
        copy=False,
        help="Date and time when the pledge was collected at POS.",
    )
    return_date = fields.Datetime(
        string="Returned On",
        readonly=True,
        copy=False,
        help="Date and time when the pledge was returned and the deposit was reversed.",
    )
    pledge_move_id = fields.Many2one("account.move", string="Pledge Move", readonly=True, copy=False)
    return_move_id = fields.Many2one("account.move", string="Return Move", readonly=True, copy=False)
    return_payment_method_id = fields.Many2one(
        "pos.payment.method",
        string="Return Payment Method",
        readonly=True,
        copy=False,
        help="POS payment method used when the pledge deposit was returned to the customer.",
    )
    return_pos_session_id = fields.Many2one(
        "pos.session",
        string="Return POS Session",
        readonly=True,
        copy=False,
        index=True,
        help="POS session where the pledge return was processed (used for closing register).",
    )
    receive_pos_session_id = fields.Many2one(
        "pos.session",
        string="Receive POS Session",
        readonly=True,
        copy=False,
        index=True,
        help="POS session where the pledge was collected on advance completion.",
    )
    return_pos_order_id = fields.Many2one(
        "pos.order",
        string="Return POS Order",
        readonly=True,
        copy=False,
        help="Refund POS order created when the pledge was returned to the customer.",
    )

    @api.depends(
        "order_id.currency_id",
        "pos_order_id.currency_id",
        "order_id.company_id.currency_id",
        "pos_order_id.company_id.currency_id",
    )
    def _compute_currency_id(self):
        for rec in self:
            if rec.order_id and rec.order_id.currency_id:
                rec.currency_id = rec.order_id.currency_id
            elif rec.pos_order_id and rec.pos_order_id.currency_id:
                rec.currency_id = rec.pos_order_id.currency_id
            elif rec.order_id and rec.order_id.company_id:
                rec.currency_id = rec.order_id.company_id.currency_id
            elif rec.pos_order_id and rec.pos_order_id.company_id:
                rec.currency_id = rec.pos_order_id.company_id.currency_id
            else:
                rec.currency_id = self.env.company.currency_id

    @api.depends("pledge_qty", "pledge_amount_unit")
    def _compute_pledge_subtotal(self):
        for rec in self:
            rec.pledge_subtotal = (rec.pledge_qty or 0.0) * (rec.pledge_amount_unit or 0.0)

    @api.depends(
        "order_id.employee_id",
        "pos_order_id.employee_id",
        "pos_order_id.advance_order_id",
        "pos_order_id.advance_order_id.employee_id",
    )
    def _compute_employee_id(self):
        for rec in self:
            order = rec.order_id or rec.pos_order_id.advance_order_id
            pos_order = rec.pos_order_id
            if order and order.employee_id:
                rec.employee_id = order.employee_id.id
            elif pos_order and pos_order.employee_id:
                rec.employee_id = pos_order.employee_id.id
            else:
                rec.employee_id = False

    def init(self):
        # Backfill links for POS-created pledge lines when possible
        # (POS order may have advance_order_id if generated from pos_advance_order flow).
        self.env.cr.execute(
            """
            UPDATE pos_advance_order_pledge pl
               SET order_id = o.advance_order_id
              FROM pos_order o
             WHERE pl.pos_order_id = o.id
               AND pl.order_id IS NULL
               AND o.advance_order_id IS NOT NULL
            """
        )
        self.env.cr.execute(
            """
            UPDATE pos_advance_order_pledge pl
               SET partner_id = o.partner_id
              FROM pos_order o
             WHERE pl.pos_order_id = o.id
               AND pl.partner_id IS NULL
               AND o.partner_id IS NOT NULL
            """
        )
        self.env.cr.execute(
            """
            UPDATE pos_advance_order_pledge
               SET state = 'active'
             WHERE state IS NULL
            """
        )
        # Only when pos.order has pledge_deposit_move_id (e.g. pos_pledge_order); skip otherwise.
        self.env.cr.execute(
            """
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'pos_order'
               AND column_name = 'pledge_deposit_move_id'
             LIMIT 1
            """
        )
        if self.env.cr.fetchone():
            self.env.cr.execute(
                """
                UPDATE pos_advance_order_pledge pl
                   SET pledge_move_id = o.pledge_deposit_move_id
                  FROM pos_order o
                 WHERE pl.pos_order_id = o.id
                   AND pl.pledge_move_id IS NULL
                   AND o.pledge_deposit_move_id IS NOT NULL
                """
            )
        self.env.cr.execute(
            """
            UPDATE pos_advance_order_pledge
               SET receive_date = create_date
             WHERE receive_date IS NULL
            """
        )

    @api.constrains("order_id", "pos_order_id")
    def _check_origin(self):
        for rec in self:
            if not rec.order_id and not rec.pos_order_id:
                raise ValidationError(_("Pledge line must be linked to an Advance Order or a POS Order."))

    @api.model
    def _pledge_is_blocked_for_vals(self, vals):
        """Site Service advance orders must never create pledge records."""
        advance = self.env["pos.advance.order"]
        if vals.get("order_id"):
            advance = advance.browse(vals["order_id"])
        elif vals.get("pos_order_id"):
            pos_order = self.env["pos.order"].browse(vals["pos_order_id"])
            if pos_order.exists():
                advance = pos_order.advance_order_id
        if advance and advance.exists() and not advance._pledge_applies():
            return advance
        return False

    @api.model_create_multi
    def create(self, vals_list):
        allowed_vals = []
        for vals in vals_list:
            blocked_advance = self._pledge_is_blocked_for_vals(vals)
            if blocked_advance:
                _logger.info(
                    "[ADVANCE_ORDER] Blocked pledge line create for site service advance %s",
                    blocked_advance.name,
                )
                continue
            allowed_vals.append(vals)
        if not allowed_vals:
            return self.browse()

        # Auto-fill order_id/partner_id when possible
        for vals in allowed_vals:
            if not vals.get("order_id") and vals.get("pos_order_id"):
                pos_order = self.env["pos.order"].browse(vals["pos_order_id"])
                if pos_order.exists() and pos_order.advance_order_id:
                    vals["order_id"] = pos_order.advance_order_id.id

            if not vals.get("partner_id") and vals.get("order_id"):
                order = self.env["pos.advance.order"].browse(vals["order_id"])
                if order.exists():
                    vals["partner_id"] = order.partner_id.id
            if not vals.get("partner_id") and vals.get("pos_order_id"):
                pos_order = self.env["pos.order"].browse(vals["pos_order_id"])
                if pos_order.exists() and pos_order.partner_id:
                    vals["partner_id"] = pos_order.partner_id.id
            if vals.get("state") not in ("pending", "cancelled") and "receive_date" not in vals:
                vals["receive_date"] = fields.Datetime.now()
        return super().create(allowed_vals)

    @api.model
    def create_from_pos(self, vals):
        """
        Called by pos_pledge frontend.
        Creates pledge line records linked to a POS order.
        Expects vals like:
          - pos_order_id
          - partner_id
          - pledge_products: [product_id, ...]
        """
        pos_order_id = vals.get("pos_order_id")
        partner_id = vals.get("partner_id")
        if not pos_order_id or not partner_id:
            raise ValidationError(_("Missing required fields for pledge creation (pos_order_id, partner_id)."))

        pos_order = self.env["pos.order"].sudo().browse(pos_order_id)
        if not pos_order.exists():
            raise ValidationError(_("POS Order not found."))

        advance_order = pos_order.advance_order_id
        if advance_order and not advance_order._pledge_applies():
            _logger.info(
                "[ADVANCE_ORDER] Skipped create_from_pos for site service advance %s on POS order %s",
                advance_order.name,
                pos_order.name,
            )
            return False

        advance_order_id = advance_order.id if advance_order else False

        pledge_product_ids = vals.get("pledge_products") or []
        if not isinstance(pledge_product_ids, list):
            pledge_product_ids = []

        # If frontend didn't send pledge_products, infer from order lines
        if not pledge_product_ids:
            pledge_product_ids = list({
                l.product_id.id
                for l in pos_order.lines.filtered(lambda l: l.product_id and l.product_id.has_pledge)
            })

        qty_by_product = defaultdict(float)
        for line in pos_order.lines.filtered(lambda l: l.product_id and l.product_id.id in pledge_product_ids):
            if line.product_id.has_pledge:
                qty_by_product[line.product_id.id] += line.qty or 0.0

        if not qty_by_product:
            raise ValidationError(_("No pledge products found to create pledge lines."))

        # Idempotent upsert to avoid duplicates when multiple flows call create_from_pos.
        # For advance orders, dedupe by (order_id, product_id). Otherwise by (pos_order_id, product_id).
        created = self.browse()
        for product_id, qty in qty_by_product.items():
            product = self.env["product.product"].browse(product_id)
            unit_amount = product.lst_price or 0.0

            if advance_order_id:
                existing = self.sudo().search(
                    [("order_id", "=", advance_order_id), ("product_id", "=", product_id)],
                    limit=1,
                )
            else:
                existing = self.sudo().search(
                    [("pos_order_id", "=", pos_order.id), ("product_id", "=", product_id)],
                    limit=1,
                )

            if existing:
                write_vals = {
                    "pos_order_id": pos_order.id,
                    "partner_id": partner_id,
                    "pledge_qty": qty,
                    "pledge_amount_unit": unit_amount,
                    "state": "active",
                    "return_date": False,
                    "return_move_id": False,
                }
                if existing.state == "returned" or not existing.receive_date:
                    write_vals["receive_date"] = fields.Datetime.now()
                existing.write(write_vals)
                created |= existing
                continue

            created |= self.sudo().create(
                {
                    "order_id": advance_order_id,
                    "pos_order_id": pos_order.id,
                    "partner_id": partner_id,
                    "product_id": product_id,
                    "pledge_qty": qty,
                    "pledge_amount_unit": unit_amount,
                    "state": "active",
                }
            )
        return created[:1].id

    @api.model
    def _resolve_return_payment_method(self, pos_order, pos_payment_method_id=None):
        """Resolve the POS payment method used to pay the customer on pledge return."""
        PaymentMethod = self.env["pos.payment.method"].sudo()
        config = (
            pos_order.config_id
            if pos_order
            else (self.order_id.pos_config_id if self.order_id else False)
        )
        if not config:
            raise UserError(_("POS configuration not found for this pledge return."))
        if pos_payment_method_id:
            pm = PaymentMethod.browse(int(pos_payment_method_id))
            if pm.exists() and pm.id in config.payment_method_ids.ids:
                return pm
            raise UserError(_("Selected payment method is not available on this POS."))
        deposit_move = (
            pos_order.pledge_deposit_move_id
            if pos_order and "pledge_deposit_move_id" in pos_order._fields
            else self.env["account.move"]
        )
        if deposit_move and deposit_move.journal_id:
            pm = config.payment_method_ids.filtered(
                lambda p: p.journal_id == deposit_move.journal_id
            )[:1]
            if pm:
                return pm
        pm = config.payment_method_ids.filtered(lambda p: p.type == "cash" and p.journal_id)[:1]
        if pm:
            return pm
        pm = config.payment_method_ids.filtered(lambda p: p.journal_id)[:1]
        if not pm:
            raise UserError(_("Configure at least one payment method on the POS to return pledges."))
        return pm

    def _resolve_return_session(self, pos_order, pos_session_id=None):
        session = False
        if pos_session_id:
            session = (
                self.env["pos.session"]
                .sudo()
                .browse(int(pos_session_id))
                .exists()
            )
        if (
            session
            and pos_order
            and session.config_id == pos_order.config_id
            and session.state in ("opened", "closing_control")
        ):
            return session
        if pos_order and pos_order.session_id.state in ("opened", "closing_control"):
            return pos_order.session_id
        if session and session.state in ("opened", "closing_control"):
            return session
        raise UserError(_("Open a POS session on this configuration to return pledges."))

    def _create_pledge_refund_pos_order(self, session, payment_method):
        """Refund pledge amount to the customer as a normal POS order (negative line)."""
        self.ensure_one()
        advance = self.order_id
        if not advance:
            raise UserError(_("This pledge is not linked to an advance order."))
        lines = [
            {
                "product_id": self.product_id.id,
                "qty": -(self.pledge_qty or 0.0),
                "price_unit": self.pledge_amount_unit or self.product_id.lst_price,
                "discount": 0.0,
                "tax_ids": [(6, 0, self.product_id.taxes_id.ids)],
                "name": _("Pledge return: %s") % self.product_id.display_name,
            }
        ]
        refund_order = advance._create_pos_order(session, lines, mark_advance_generated=False)
        advance._pay_pos_order_multi(refund_order, [(payment_method, refund_order.amount_total)])
        return refund_order

    def action_return_pledge(self, pos_payment_method_id=None, pos_session_id=None):
        """Return pledge to customer via a refund POS order and selected payment method."""
        ctx = self.env.context
        if pos_payment_method_id is None:
            pos_payment_method_id = ctx.get("pos_payment_method_id")
        if pos_session_id is None:
            pos_session_id = ctx.get("pos_session_id")

        for pledge in self:
            if pledge.state == "returned":
                continue
            if pledge.state != "active":
                raise UserError(_("Only active pledges can be returned."))

            pos_order = pledge.pos_order_id
            advance = pledge.order_id
            if not pos_order and advance:
                linked = pledge.search(
                    [("order_id", "=", advance.id), ("pos_order_id", "!=", False)],
                    limit=1,
                )
                pos_order = linked.pos_order_id if linked else advance.remaining_pos_order_id

            config = (
                pos_order.config_id
                if pos_order
                else (advance.pos_config_id if advance else False)
            )
            if not config:
                raise UserError(_("Cannot resolve POS configuration for this pledge return."))

            session = pledge._resolve_return_session(pos_order, pos_session_id)
            return_pm = pledge._resolve_return_payment_method(pos_order or self.env["pos.order"], pos_payment_method_id)
            refund_order = pledge._create_pledge_refund_pos_order(session, return_pm)

            pledge.write(
                {
                    "state": "returned",
                    "return_date": fields.Datetime.now(),
                    "return_payment_method_id": return_pm.id,
                    "return_pos_session_id": session.id,
                    "return_pos_order_id": refund_order.id,
                    "pos_order_id": pledge.pos_order_id.id or (pos_order.id if pos_order else False),
                }
            )
            _logger.info(
                "[PLEDGE] Returned pledge line %s via refund order %s pm=%s session=%s",
                pledge.id,
                refund_order.name,
                return_pm.display_name,
                session.name,
            )
        return True

    def action_cancel(self):
        self.write({"state": "cancelled"})
        return True

