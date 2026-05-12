# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


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
        help="Filled from the linked Advance Order employee when With Employee is enabled.",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        domain=[("available_in_pos", "=", True)],
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
            ("active", "Active"),
            ("returned", "Returned"),
            ("cancelled", "Cancelled"),
        ],
        string="State",
        default="active",
        index=True,
    )
    return_date = fields.Datetime(string="Return Date", readonly=True, copy=False)
    pledge_move_id = fields.Many2one("account.move", string="Pledge Move", readonly=True, copy=False)
    return_move_id = fields.Many2one("account.move", string="Return Move", readonly=True, copy=False)

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
        "order_id.with_employee",
        "order_id.employee_id",
        "pos_order_id.advance_order_id",
        "pos_order_id.advance_order_id.with_employee",
        "pos_order_id.advance_order_id.employee_id",
    )
    def _compute_employee_id(self):
        for rec in self:
            order = rec.order_id or rec.pos_order_id.advance_order_id
            if order and order.with_employee and order.employee_id:
                rec.employee_id = order.employee_id.id
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

    @api.constrains("order_id", "pos_order_id")
    def _check_origin(self):
        for rec in self:
            if not rec.order_id and not rec.pos_order_id:
                raise ValidationError(_("Pledge line must be linked to an Advance Order or a POS Order."))

    @api.model_create_multi
    def create(self, vals_list):
        # Auto-fill order_id/partner_id when possible
        for vals in vals_list:
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
        return super().create(vals_list)

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

        advance_order_id = pos_order.advance_order_id.id if getattr(pos_order, "advance_order_id", False) else False

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
            unit_amount = product.pledge_amount or 0.0

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
                existing.write(
                    {
                        "pos_order_id": pos_order.id,
                        "partner_id": partner_id,
                        "pledge_qty": qty,
                        "pledge_amount_unit": unit_amount,
                        "state": "active",
                        "return_date": False,
                        "return_move_id": False,
                    }
                )
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

    def action_return_pledge(self):
        """Reverse pledge deposit move and mark pledge lines returned."""
        PledgeLine = self.env["pos.advance.order.pledge"]
        for pledge in self:
            if pledge.state == "returned" and pledge.return_move_id:
                continue
            if pledge.state != "active":
                raise UserError(_("Only active pledges can be returned."))

            pos_order = pledge.pos_order_id
            advance = pledge.order_id
            if pos_order:
                related_lines = PledgeLine.search(
                    [("pos_order_id", "=", pos_order.id), ("state", "=", "active")]
                )
            elif advance:
                related_lines = PledgeLine.search(
                    [("order_id", "=", advance.id), ("state", "=", "active")]
                )
                linked_pos = related_lines.filtered("pos_order_id")[:1]
                pos_order = (
                    linked_pos.pos_order_id
                    if linked_pos
                    else advance.pledge_pos_order_id
                )
            else:
                raise UserError(
                    _(
                        "This pledge is not linked to a POS order or an advance order. "
                        "Open the related advance order and complete the pledge collection on POS, or contact an administrator."
                    )
                )

            if not related_lines:
                related_lines = pledge

            move = False
            for line in related_lines:
                if line.pledge_move_id:
                    move = line.pledge_move_id
                    break
            if not move and pos_order:
                move = pos_order.pledge_deposit_move_id
            if not move or move.state != "posted":
                raise UserError(_("No posted pledge journal entry is linked to this pledge."))

            existing_return = related_lines.filtered(lambda l: l.return_move_id)[:1]
            reverse_move = existing_return.return_move_id
            if not reverse_move:
                # POS users have read-only access to account.move; reversal must run elevated.
                move_sudo = move.sudo()
                ref_name = (
                    (pos_order and (pos_order.name or pos_order.pos_reference))
                    or (advance and advance.name)
                    or move_sudo.ref
                    or ""
                )
                reverse_moves = move_sudo._reverse_moves(
                    [
                        {
                            "date": fields.Date.context_today(pledge),
                            "ref": _("Pledge return - %s") % ref_name,
                        }
                    ],
                    cancel=False,
                )
                reverse_moves.sudo().action_post()
                reverse_move = reverse_moves[:1]

            related_lines.write(
                {
                    "state": "returned",
                    "return_date": fields.Datetime.now(),
                    "return_move_id": reverse_move.id,
                    "pledge_move_id": move.id,
                }
            )

            sess = pos_order.session_id if pos_order else False
            if sess and sess.state in ("opened", "closing_control"):
                sess.invalidate_recordset(
                    ["cash_register_balance_end", "cash_register_difference"]
                )
        return True

    def action_cancel(self):
        self.write({"state": "cancelled"})
        return True

