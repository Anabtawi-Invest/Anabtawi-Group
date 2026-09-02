# -*- coding: utf-8 -*-
"""B1 accounting-first pledge return (legacy + current pos_pledge_order flow)."""

import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero

_logger = logging.getLogger(__name__)


class PosAdvanceOrderPledgeReturn(models.Model):
    _inherit = "pos.advance.order.pledge"

    def _resolve_pledge_collection_order(self):
        """Original POS order where the pledge deposit was collected (never a REFUND order)."""
        self.ensure_one()
        pos_order = self._resolve_pledge_source_order()
        if not pos_order:
            return pos_order
        visited = set()
        order = pos_order.sudo()
        while order and order.id not in visited:
            visited.add(order.id)
            is_refund = bool(getattr(order, "is_refund", False)) or (order.amount_total or 0.0) < 0.0
            if is_refund and order.refunded_order_id:
                order = order.refunded_order_id.sudo()
                continue
            break
        return order

    @api.model
    def _resolve_return_payment_method(self, pos_order, pos_payment_method_id=None, pos_session_id=None):
        """Resolve payout method; prefer the **current** POS session config when returning from POS."""
        PaymentMethod = self.env["pos.payment.method"].sudo()
        config = False
        if pos_session_id:
            session = self.env["pos.session"].sudo().browse(int(pos_session_id)).exists()
            if session:
                config = session.config_id
        collection_order = pos_order.sudo() if pos_order else False
        if collection_order and collection_order.is_refund and collection_order.refunded_order_id:
            collection_order = collection_order.refunded_order_id.sudo()
        if not config and collection_order:
            config = collection_order.config_id
        if not config:
            pledge = self[:1]
            if pledge.order_id and pledge.order_id.pos_config_id:
                config = pledge.order_id.pos_config_id
        if not config:
            raise UserError(_("POS configuration not found for this pledge return."))
        if pos_payment_method_id:
            pm = PaymentMethod.browse(int(pos_payment_method_id))
            if pm.exists() and pm.id in config.payment_method_ids.ids:
                return pm
            raise UserError(_("Selected payment method is not available on this POS."))
        deposit_move = (
            collection_order.pledge_deposit_move_id
            if collection_order
            and "pledge_deposit_move_id" in collection_order._fields
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

    def _get_pledge_deposit_move(self, collection_order):
        """Posted deposit move for this pledge line."""
        self.ensure_one()
        move = self.pledge_move_id
        if move and move.state == "posted":
            return move
        if (
            collection_order
            and "pledge_deposit_move_id" in collection_order._fields
            and collection_order.pledge_deposit_move_id
            and collection_order.pledge_deposit_move_id.state == "posted"
        ):
            return collection_order.pledge_deposit_move_id
        return self.env["account.move"]

    def _normalize_legacy_pledge_row(self, collection_order):
        """Repair rows corrupted by the old POS product-refund return flow."""
        self.ensure_one()
        vals = {}
        if collection_order and self.pos_order_id != collection_order:
            vals["pos_order_id"] = collection_order.id
        qty = self.pledge_qty or 0.0
        if qty < 0:
            vals["pledge_qty"] = abs(qty)
        if self.return_pos_order_id and self.state == "active":
            vals["return_pos_order_id"] = False
        if vals:
            self.sudo().write(vals)

    def _action_return_pledges_accounting(self, pledges, pos_payment_method_id=None, pos_session_id=None):
        """Reverse pledge deposit JE and mark pledge lines returned (B1 / legacy pos.pledge flow)."""
        PledgeLine = self.env["pos.advance.order.pledge"]
        results = []

        groups = {}
        collection_orders = {}
        for pledge in pledges:
            collection_order = pledge._resolve_pledge_collection_order()
            if not collection_order:
                raise UserError(
                    _(
                        "Cannot return pledge for %(product)s: original POS order was not found.",
                        product=pledge.product_id.display_name,
                    )
                )
            pledge._normalize_legacy_pledge_row(collection_order)
            collection_orders[collection_order.id] = collection_order
            groups.setdefault(collection_order.id, PledgeLine)
            groups[collection_order.id] |= pledge

        for order_id, group_pledges in groups.items():
            collection_order = collection_orders[order_id]
            return_pm = group_pledges[:1]._resolve_return_payment_method(
                collection_order,
                pos_payment_method_id,
                pos_session_id=pos_session_id,
            )

            related_lines = group_pledges
            all_active = PledgeLine.search(
                [
                    ("pos_order_id", "=", collection_order.id),
                    ("state", "=", "active"),
                ]
            )
            if len(all_active) > len(related_lines):
                raise UserError(
                    _(
                        "Order %(order)s has %(total)s active pledge(s). "
                        "Return all active pledges on this order in one operation.",
                        order=collection_order.display_name,
                        total=len(all_active),
                    )
                )

            move = self.env["account.move"]
            for line in related_lines:
                candidate = line._get_pledge_deposit_move(collection_order)
                if candidate:
                    move = candidate
                    break
            if not move or move.state != "posted":
                raise UserError(
                    _(
                        "No posted pledge journal entry is linked to order %(order)s. "
                        "Cannot reverse pledge deposit.",
                        order=collection_order.display_name,
                    )
                )

            existing_return = related_lines.filtered(lambda l: l.return_move_id)[:1]
            reverse_move = existing_return.return_move_id
            if not reverse_move:
                move_sudo = move.sudo()
                reverse_moves = move_sudo._reverse_moves(
                    [
                        {
                            "date": fields.Date.context_today(group_pledges[:1]),
                            "ref": _("Pledge return - %s") % (collection_order.name or collection_order.display_name),
                        }
                    ],
                    cancel=False,
                )
                reverse_moves.sudo().action_post()
                reverse_move = reverse_moves[:1]

            sess = False
            if pos_session_id:
                refund_session = (
                    self.env["pos.session"]
                    .sudo()
                    .browse(int(pos_session_id))
                    .exists()
                )
                if refund_session and refund_session.state in ("opened", "closing_control"):
                    sess = refund_session
            if not sess and collection_order.session_id.state in ("opened", "closing_control"):
                sess = collection_order.session_id

            related_lines.write(
                {
                    "state": "returned",
                    "return_date": fields.Datetime.now(),
                    "return_move_id": reverse_move.id,
                    "return_payment_method_id": return_pm.id,
                    "pledge_move_id": move.id,
                    "pos_order_id": collection_order.id,
                    "return_pos_order_id": False,
                }
            )
            if sess:
                related_lines.write({"return_pos_session_id": sess.id})
                sess.invalidate_recordset(
                    ["cash_register_balance_end", "cash_register_difference"]
                )

            amount = sum(abs(line.pledge_subtotal or 0.0) for line in related_lines)
            results.append(
                {
                    "pledge_ids": related_lines.ids,
                    "return_move_id": reverse_move.id,
                    "return_move_name": reverse_move.name,
                    "origin_order_name": collection_order.name,
                    "payment_method_name": return_pm.display_name,
                    "amount": amount,
                }
            )
            _logger.info(
                "[PLEDGE] Returned %s pledge line(s) via accounting reversal move=%s pm=%s origin=%s amount=%s",
                len(related_lines),
                reverse_move.name,
                return_pm.display_name,
                collection_order.name,
                amount,
            )

        if len(results) == 1:
            return results[0]
        return {
            "results": results,
            "count": len(results),
            "pledge_count": len(pledges),
        }

    def action_return_pledges(self, pledge_ids=None, pos_payment_method_id=None, pos_session_id=None):
        """Return pledges via deposit journal reversal (B1), not menu-product POS refunds."""
        ctx = self.env.context
        if pos_payment_method_id is None:
            pos_payment_method_id = ctx.get("pos_payment_method_id")
        if pos_session_id is None:
            pos_session_id = ctx.get("pos_session_id")

        pledges = self.browse(pledge_ids).exists() if pledge_ids else self
        pledges = pledges.filtered(lambda p: p.state != "returned")
        if not pledges:
            raise UserError(_("Please select at least one active pledge to return."))

        invalid = pledges.filtered(lambda p: p.state != "active")
        if invalid:
            raise UserError(_("Only active pledges can be returned."))

        return self._action_return_pledges_accounting(
            pledges,
            pos_payment_method_id=pos_payment_method_id,
            pos_session_id=pos_session_id,
        )

    def action_return_pledge(self, pos_payment_method_id=None, pos_session_id=None):
        """Return selected pledge(s) via accounting reversal."""
        return self.action_return_pledges(
            pledge_ids=self.ids,
            pos_payment_method_id=pos_payment_method_id,
            pos_session_id=pos_session_id,
        )
