# -*- coding: utf-8 -*-

import logging
from collections import defaultdict
from datetime import datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PURGE_CTX = {
    "pos_historical_purge": True,
    "force_delete": True,
    "skip_invoice_sync": True,
    "check_move_validity": False,
}


class PosPurgeService(models.AbstractModel):
    """Shared purge / dry-run logic for POS historical cleanup."""

    _name = "pos.purge.service"
    _description = "POS Historical Purge Service"

    # -------------------------------------------------------------------------
    # Scope
    # -------------------------------------------------------------------------

    @api.model
    def _cutoff_datetime(self, cutoff_date, company):
        """Start of cutoff day in company/user timezone, stored as naive UTC datetime."""
        tz_name = company.partner_id.tz or self.env.user.tz or "UTC"
        try:
            import pytz
            tz = pytz.timezone(tz_name)
            local_start = tz.localize(datetime.combine(cutoff_date, time.min))
            return local_start.astimezone(pytz.UTC).replace(tzinfo=None)
        except Exception:
            return datetime.combine(cutoff_date, time.min)

    POS_ORDER_STATES = ("draft", "cancel", "paid", "done")

    @api.model
    def _order_domain(self, company, cutoff_date, order_states=None):
        cutoff_dt = self._cutoff_datetime(cutoff_date, company)
        domain = [
            ("company_id", "=", company.id),
            ("date_order", "<", cutoff_dt),
        ]
        if order_states:
            domain.append(("state", "in", list(order_states)))
        return domain

    @api.model
    def _expand_refund_clusters(self, orders):
        """Include refund-related orders so clusters are purged together."""
        PosOrder = self.env["pos.order"].sudo()
        cluster = orders
        for _i in range(10):
            related = PosOrder.search([
                "|",
                ("lines.refunded_orderline_id.order_id", "in", cluster.ids),
                ("lines.refund_orderline_ids.order_id", "in", cluster.ids),
            ])
            new_orders = related - cluster
            if not new_orders:
                break
            cluster |= new_orders
        return cluster

    @api.model
    def collect_orders(self, company, cutoff_date, options=None, expand_refunds=True):
        options = options or {}
        order_states = options.get("order_states")
        orders = self.env["pos.order"].sudo().search(
            self._order_domain(company, cutoff_date, order_states=order_states)
        )
        if expand_refunds:
            orders = self._expand_refund_clusters(orders)
            # Re-apply state filter after expanding refund clusters
            if order_states:
                orders = orders.filtered(lambda o: o.state in order_states)
        return orders

    # -------------------------------------------------------------------------
    # Blockers (dry-run)
    # -------------------------------------------------------------------------

    @api.model
    def _check_einvoice_blockers(self, orders, block_submitted):
        """Block purge when invoices were submitted to e-invoicing (JoFotara / generic EDI)."""
        blockers = []
        if not block_submitted:
            return blockers

        Move = self.env["account.move"]
        jo_state_field = "l10n_jo_edi_state" in Move._fields
        generic_edi_field = "edi_state" in Move._fields

        for order in orders.filtered("account_move"):
            move = order.account_move

            # Jordan — JoFotara (l10n_jo_edi), often referred to as Jo Fawtara / Fawtara
            if jo_state_field and move.l10n_jo_edi_state in ("sent", "demo"):
                blockers.append({
                    "level": "error",
                    "category": "jo_fotara",
                    "order_id": order.id,
                    "message": _(
                        "Order %(order)s has invoice %(inv)s submitted to JoFotara "
                        "(state: %(state)s). Cancel on the tax platform before purging.",
                        order=order.name,
                        inv=move.name,
                        state=move.l10n_jo_edi_state,
                    ),
                })
                continue

            # Generic account_edi (e.g. other countries) — not ZATCA-specific
            if generic_edi_field and move.edi_state == "sent":
                blockers.append({
                    "level": "error",
                    "category": "einvoice",
                    "order_id": order.id,
                    "message": _(
                        "Order %(order)s has an e-invoice already sent to the government: %(inv)s.",
                        order=order.name,
                        inv=move.name,
                    ),
                })

        return blockers

    @api.model
    def _check_custom_blockers(self, orders):
        blockers = []
        # pos.advance.payment (advance module)
        if "pos.advance.payment" in self.env:
            Advance = self.env["pos.advance.payment"].sudo()
            for adv in Advance.search([("pos_order_id", "in", orders.ids)]):
                if adv.state not in ("cancelled", "cancel"):
                    blockers.append({
                        "level": "error",
                        "category": "advance",
                        "order_id": adv.pos_order_id.id,
                        "message": _("Advance payment %s linked to order %s (state %s).", adv.name, adv.pos_order_id.name, adv.state),
                    })
        # pos.advance.order
        if "pos.advance.order" in self.env:
            AdvOrder = self.env["pos.advance.order"].sudo()
            fk_fields = [
                "advance_pos_order_id",
                "remaining_pos_order_id",
                "pledge_pos_order_id",
                "refund_advance_pos_order_id",
                "return_pledge_pos_order_id",
            ]
            for fname in fk_fields:
                if fname not in AdvOrder._fields:
                    continue
                linked = AdvOrder.search([(fname, "in", orders.ids)])
                for rec in linked:
                    blockers.append({
                        "level": "error",
                        "category": "advance_order",
                        "order_id": getattr(rec, fname).id,
                        "message": _("Advance order %s references POS order via %s.", rec.display_name, fname),
                    })
        # pos.pledge
        if "pos.pledge" in self.env:
            Pledge = self.env["pos.pledge"].sudo()
            for pledge in Pledge.search([("pos_order_id", "in", orders.ids)]):
                if pledge.state not in ("returned", "cancelled"):
                    blockers.append({
                        "level": "warning",
                        "category": "pledge",
                        "order_id": pledge.pos_order_id.id,
                        "message": _("Pledge %s for order %s (state %s).", pledge.name, pledge.pos_order_id.name, pledge.state),
                    })
        return blockers

    @api.model
    def _session_scope_analysis(self, orders):
        """Classify sessions as full_purge vs mixed."""
        by_session = defaultdict(lambda: self.env["pos.order"])
        for order in orders:
            if order.session_id:
                by_session[order.session_id] |= order

        full_sessions = self.env["pos.session"]
        mixed_sessions = self.env["pos.session"]
        for session, scoped_orders in by_session.items():
            if len(scoped_orders) == len(session.order_ids):
                full_sessions |= session
            else:
                mixed_sessions |= session
        return full_sessions, mixed_sessions

    @api.model
    def _state_breakdown(self, orders):
        labels = dict(
            self.env["pos.order"].fields_get(["state"], ["selection"])["state"]["selection"]
        )
        breakdown = {}
        for state in self.POS_ORDER_STATES:
            count = len(orders.filtered(lambda o, s=state: o.state == s))
            if count:
                breakdown[state] = {"count": count, "label": labels.get(state, state)}
        return breakdown

    @api.model
    def dry_run(self, company, cutoff_date, options):
        orders = self.collect_orders(company, cutoff_date, options=options)
        full_sessions, mixed_sessions = self._session_scope_analysis(orders)

        blockers = []
        block_submitted = options.get(
            "block_submitted_einvoices",
            options.get("skip_zatca_sent", True),  # legacy key
        )
        blockers += self._check_einvoice_blockers(orders, block_submitted)
        blockers += self._check_custom_blockers(orders)

        for session in mixed_sessions:
            blockers.append({
                "level": "warning",
                "category": "session",
                "order_id": False,
                "message": _(
                    "Session %s has orders both before and after the cutoff. "
                    "Session closing entry will NOT be auto-removed.",
                    session.name,
                ),
            })

        open_sessions = orders.session_id.filtered(lambda s: s.state not in ("closed",))
        for session in open_sessions:
            blockers.append({
                "level": "error",
                "category": "session",
                "order_id": False,
                "message": _("Session %s is not closed (state %s).", session.name, session.state),
            })

        done_pickings = orders.picking_ids.filtered(lambda p: p.state == "done")
        if done_pickings and options.get("stock_handling") == "block":
            blockers.append({
                "level": "error",
                "category": "stock",
                "order_id": False,
                "message": _("%s done stock picking(s) require reversal or a different stock handling option.", len(done_pickings)),
            })

        stats = {
            "order_count": len(orders),
            "session_count": len(orders.session_id),
            "full_session_count": len(full_sessions),
            "mixed_session_count": len(mixed_sessions),
            "invoice_count": len(orders.filtered("account_move")),
            "picking_count": len(orders.picking_ids),
            "done_picking_count": len(done_pickings),
            "payment_move_count": len(orders.payment_ids.mapped("account_move_id")),
            "order_states": options.get("order_states") or list(self.POS_ORDER_STATES),
            "state_breakdown": self._state_breakdown(orders),
        }
        return {
            "orders": orders,
            "full_sessions": full_sessions,
            "mixed_sessions": mixed_sessions,
            "blockers": blockers,
            "stats": stats,
        }

    # -------------------------------------------------------------------------
    # Accounting helpers
    # -------------------------------------------------------------------------

    @api.model
    def _safe_unlink_account_moves(self, moves):
        moves = moves.sudo().exists()
        if not moves:
            return
        moves.mapped("line_ids").remove_move_reconcile()
        posted = moves.filtered(lambda m: m.state == "posted")
        if posted:
            posted.with_context(**PURGE_CTX).button_draft()
        moves.exists().with_context(**PURGE_CTX).unlink()

    @api.model
    def _safe_unlink_account_payments(self, payments):
        """Cancel then unlink session bank payments (never drop move_id while still paid)."""
        payments = payments.sudo().exists()
        if not payments:
            return
        for payment in payments:
            move = payment.move_id
            if move:
                move.line_ids.remove_move_reconcile()
            if payment.state not in ("draft", "canceled", "rejected"):
                payment.with_context(**PURGE_CTX).action_cancel()
            payment.with_context(**PURGE_CTX).unlink()

    @api.model
    def _collect_order_moves(self, order):
        moves = self.env["account.move"]
        if order.account_move:
            moves |= order.account_move
        moves |= order.reversed_move_ids
        moves |= order.payment_ids.mapped("account_move_id")
        return moves.filtered(lambda m: m.exists())

    # -------------------------------------------------------------------------
    # Stock helpers
    # -------------------------------------------------------------------------

    @api.model
    def _set_return_wizard_quantities(self, wizard):
        """Mirror stock.return.picking.action_create_returns_all quantity logic."""
        for return_line in wizard.product_return_moves:
            stock_move = return_line.move_id
            if (
                not stock_move
                or stock_move.state == "cancel"
                or stock_move.location_dest_usage == "inventory"
            ):
                continue
            quantity = stock_move.quantity
            for move in stock_move.move_dest_ids:
                if (
                    not move.origin_returned_move_id
                    or move.origin_returned_move_id != stock_move
                ):
                    continue
                quantity -= move.quantity
            return_line.quantity = stock_move.product_uom.round(quantity)

    @api.model
    def _reverse_done_picking(self, picking):
        ReturnWizard = self.env["stock.return.picking"].sudo()
        if not picking._can_return():
            raise UserError(_("Picking %s cannot be returned.", picking.name))
        wizard = ReturnWizard.with_context(
            active_id=picking.id,
            active_model="stock.picking",
        ).create({"picking_id": picking.id})
        self._set_return_wizard_quantities(wizard)

        returnable = wizard.product_return_moves.filtered(
            lambda line: line.move_id and not line.uom_id.is_zero(line.quantity)
        )
        if not returnable:
            _logger.info(
                "Picking %s has no returnable quantity (already returned); detaching from POS order.",
                picking.name,
            )
            picking.write({"pos_order_id": False})
            return picking

        action = wizard.action_create_returns()
        return_picking = self.env["stock.picking"].browse(action["res_id"])
        for move in return_picking.move_ids:
            if move.product_uom.is_zero(move.quantity):
                move.quantity = move.product_uom_qty
        return_picking.move_ids._action_done()
        return return_picking

    @api.model
    def _purge_order_stock(self, order, stock_handling):
        pickings = order.picking_ids
        for picking in pickings:
            if picking.state in ("draft", "cancel"):
                if picking.state != "cancel":
                    picking.action_cancel()
                picking.unlink()
            elif picking.state == "done":
                if stock_handling == "reverse":
                    self._reverse_done_picking(picking)
                elif stock_handling == "skip":
                    picking.write({"pos_order_id": False})
                else:
                    raise UserError(
                        _("Cannot purge order %s: done picking %s.", order.name, picking.name)
                    )
            else:
                picking.action_cancel()
                picking.unlink()

    # -------------------------------------------------------------------------
    # Custom cleanup
    # -------------------------------------------------------------------------

    @api.model
    def _purge_custom_records(self, orders):
        orders = orders.sudo()
        if "pos.pledge" in self.env:
            pledges = self.env["pos.pledge"].sudo().search([("pos_order_id", "in", orders.ids)])
            if pledges and "state" in pledges._fields:
                pledges.write({"state": "returned"})
            pledges.unlink()

        if "pos.advance.payment" in self.env:
            advances = self.env["pos.advance.payment"].sudo().search([("pos_order_id", "in", orders.ids)])
            for adv in advances:
                for fname in ("transfer_move_id", "invoice_id", "completion_move_id"):
                    move = adv[fname]
                    if move:
                        self._safe_unlink_account_moves(move)
                if adv.advance_account_payment_id:
                    pay = adv.advance_account_payment_id
                    if pay.move_id:
                        self._safe_unlink_account_moves(pay.move_id)
                    pay.unlink()
                if "state" in adv._fields:
                    adv.write({"state": "cancelled"})
            advances.unlink()

        if "pos.advance.order" in self.env:
            AdvOrder = self.env["pos.advance.order"].sudo()
            fk_fields = [
                "advance_pos_order_id",
                "remaining_pos_order_id",
                "pledge_pos_order_id",
                "refund_advance_pos_order_id",
                "return_pledge_pos_order_id",
            ]
            clauses = [
                (fname, "in", orders.ids)
                for fname in fk_fields
                if fname in AdvOrder._fields
            ]
            if len(clauses) == 1:
                domain = clauses
            elif len(clauses) > 1:
                domain = ["|"] * (len(clauses) - 1) + clauses
            else:
                domain = []
            if domain:
                adv_orders = AdvOrder.search(domain)
                for rec in adv_orders:
                    if rec.advance_liability_move_id:
                        self._safe_unlink_account_moves(rec.advance_liability_move_id)
                    if rec.advance_account_payment_id and rec.advance_account_payment_id.move_id:
                        self._safe_unlink_account_moves(rec.advance_account_payment_id.move_id)
                adv_orders.unlink()

    # -------------------------------------------------------------------------
    # Chatter / SQL housekeeping
    # -------------------------------------------------------------------------

    @api.model
    def _purge_chatter_sql(self, order_ids):
        if not order_ids:
            return
        cr = self.env.cr
        ids_tuple = tuple(order_ids)

        def table_exists(name):
            cr.execute("SELECT to_regclass(%s)", (f"public.{name}",))
            return bool(cr.fetchone()[0])

        cr.execute(
            "DELETE FROM mail_message WHERE model = 'pos.order' AND res_id IN %s",
            (ids_tuple,),
        )
        cr.execute(
            "DELETE FROM mail_followers WHERE res_model = 'pos.order' AND res_id IN %s",
            (ids_tuple,),
        )
        cr.execute(
            "DELETE FROM ir_attachment WHERE res_model = 'pos.order' AND res_id IN %s",
            (ids_tuple,),
        )
        if table_exists("rating_rating"):
            cr.execute(
                "DELETE FROM rating_rating WHERE res_model = 'pos.order' AND res_id IN %s",
                (ids_tuple,),
            )

    # -------------------------------------------------------------------------
    # Order / session purge
    # -------------------------------------------------------------------------

    @api.model
    def purge_order(self, order, options):
        order = order.sudo()
        stock_handling = options.get("stock_handling", "reverse")

        self._purge_custom_records(order)

        order_name = order.name
        moves = self._collect_order_moves(order)
        self._safe_unlink_account_moves(moves)

        self._purge_order_stock(order, stock_handling)

        # Break links before unlink
        order.with_context(**PURGE_CTX).write({"account_move": False})
        if order.reversed_move_ids:
            order.reversed_move_ids.with_context(**PURGE_CTX).write(
                {"reversed_pos_order_id": False}
            )

        cr = self.env.cr
        cr.execute(
            "DELETE FROM stock_reference_pos_order_rel WHERE pos_order_id = %s",
            (order.id,),
        )

        # pos.order.write blocks changing paid/done → cancel; SQL is required before ORM unlink.
        if order.state not in ("draft", "cancel"):
            cr.execute(
                "UPDATE pos_order SET state = 'cancel' WHERE id = %s",
                (order.id,),
            )
            order.invalidate_recordset(["state"])

        order_id = order.id
        order.with_context(**PURGE_CTX).unlink()
        self._purge_chatter_sql([order_id])
        _logger.info("Purged POS order %s (id=%s)", order_name, order_id)
        return True

    @api.model
    def purge_session(self, session, options):
        session = session.sudo()
        if session.order_ids:
            raise UserError(_("Session %s still has orders.", session.name))

        self._safe_unlink_account_payments(session.bank_payment_ids)

        for st_line in session.statement_line_ids:
            move = st_line.move_id
            st_line.unlink()
            if move and move.exists():
                self._safe_unlink_account_moves(move)

        for picking in session.picking_ids.filtered(lambda p: not p.pos_order_id):
            if picking.state == "done" and options.get("stock_handling") == "reverse":
                self._reverse_done_picking(picking)
            elif picking.state not in ("done",):
                if picking.state != "cancel":
                    picking.action_cancel()
                picking.unlink()
            else:
                picking.write({"pos_session_id": False, "pos_order_id": False})

        if session.move_id:
            self._safe_unlink_account_moves(session.move_id)
            session.write({"move_id": False})

        session.unlink()
        return True

    @api.model
    def run_purge(self, company, cutoff_date, options):
        dry = self.dry_run(company, cutoff_date, options)
        errors = [b for b in dry["blockers"] if b["level"] == "error"]
        if errors and not options.get("ignore_blockers"):
            raise UserError(
                _("Purge blocked by %s error(s). Run dry-run for details.\n%s")
                % (len(errors), "\n".join(e["message"] for e in errors[:10]))
            )

        orders = dry["orders"]
        batch_size = options.get("batch_size", 50)
        log = []
        order_ids = orders.ids
        for i in range(0, len(order_ids), batch_size):
            batch = self.env["pos.order"].sudo().browse(order_ids[i : i + batch_size])
            for order in batch:
                order_name = order.name
                try:
                    with self.env.cr.savepoint():
                        self.purge_order(order, options)
                    log.append({"order": order_name, "status": "ok"})
                except Exception as exc:
                    _logger.exception("Purge failed for %s", order.name)
                    log.append({"order": order.name, "status": "error", "error": str(exc)})
                    if options.get("stop_on_error"):
                        raise

        if options.get("purge_sessions"):
            for session in dry["full_sessions"].sudo().exists():
                session_name = session.name
                try:
                    with self.env.cr.savepoint():
                        self.purge_session(session, options)
                    log.append({"order": session_name, "status": "session_ok"})
                except Exception as exc:
                    _logger.exception("Session purge failed for %s", session_name)
                    log.append(
                        {"order": session_name, "status": "session_error", "error": str(exc)}
                    )
                    if options.get("stop_on_error"):
                        raise

        self.env.invalidate_all()
        return {"log": log, "dry": dry}
