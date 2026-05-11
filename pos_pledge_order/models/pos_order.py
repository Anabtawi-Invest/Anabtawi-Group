# -*- coding: utf-8 -*-
from odoo import models, api, fields, _
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools import float_compare, float_repr
import logging

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    pledge_id = fields.Many2one(
        'pos.pledge',
        string='Pledge Record',
        readonly=True
    )
    pledge_collection_pos_order_id = fields.Many2one(
        'pos.order',
        string='Pledge Collection POS Order (legacy)',
        readonly=True,
        copy=False,
        help='Legacy: separate POS order used before pledge was posted as accounting only.',
    )
    pledge_deposit_move_id = fields.Many2one(
        'account.move',
        string='Pledge Deposit Entry',
        readonly=True,
        copy=False,
        help='Posted as: Dr liquidity / Cr Pledge Liability Account from POS config (pledge not in pos.payment).',
    )
    pledge_snapshot_product_ids = fields.Many2many(
        'product.product',
        'pos_order_pledge_snapshot_product_rel',
        'pos_order_id',
        'product_id',
        string='Pledge Products Snapshot',
        readonly=True,
        copy=False,
    )
    is_pledge_generated = fields.Boolean(
        string='Pledge Generated Order',
        default=False,
        help='Technical flag for POS orders generated automatically by pledge flow.',
    )

    has_pledge = fields.Boolean(
        string='Has Pledge',
        compute='_compute_has_pledge',
        store=True
    )
    
    pledge_payments_created = fields.Boolean(
        string='Pledge Payments Created',
        default=False,
        help='Indicates if pledge/employee/delivery payments have been created'
    )
    
    has_employee_service = fields.Boolean(
        string='Has Employee Service',
        default=False,
        help='Indicates if this order contains employee service products'
    )
    
    employee_id = fields.Many2one(
        'hr.employee',
        string='Service Employee',
        help='Employee associated with this order for service delivery'
    )
    
    pledge_product_qty = fields.Integer(
        string='Pledge Product Quantity',
        default=0,
        help='Total quantity of pledge products in this order'
    )
    
    total_pledge_amount = fields.Monetary(
        string='Total Pledge Amount',
        currency_field='currency_id',
        help='Total amount for pledge products in this order'
    )

    @api.model
    def _order_fields(self, ui_order):
        """Read employee_id from UI order"""
        vals = super()._order_fields(ui_order)
        # Get employee_id from UI order
        employee_id = ui_order.get('employee_id', False)
        if employee_id:
            vals['employee_id'] = employee_id
        _logger.info("[PLEDGE] _order_fields: employee_id = %s", employee_id)
        return vals

    @api.depends('lines.product_id.has_pledge', 'total_pledge_amount')
    def _compute_has_pledge(self):
        for order in self:
            has_line_pledge = any(
                line.product_id and line.product_id.has_pledge for line in order.lines
            )
            has_snapshot = (order.total_pledge_amount or 0.0) > 0
            order.has_pledge = has_line_pledge or has_snapshot

    def _create_pledge_payments(self):
        """
        Kept for backward compatibility.
        Independent payment creation is disabled in this module variant.
        """
        _logger.info("[PLEDGE] _create_pledge_payments is disabled.")
        return True

    @staticmethod
    def _pledge_sync_line_qty(vals):
        """Quantity on POS sync line command (qty is ORM name; some payloads use quantity)."""
        if not isinstance(vals, dict):
            return 0.0
        raw = vals.get("qty")
        if raw is None:
            raw = vals.get("quantity")
        if raw is None or raw is False:
            return 0.0
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0

    def _compute_pledge_from_lines(self):
        """Return (total_pledge_amount, pledge_product_ids, total_pledge_qty) from pledged order lines."""
        self.ensure_one()
        total_pledge_amount = 0.0
        pledge_product_ids = []
        total_pledge_qty = 0.0
        for line in self.lines.filtered(lambda l: l.product_id):
            if not line.product_id.has_pledge:
                continue
            qty = line.qty or 0.0
            unit_pledge = line.product_id.pledge_amount or 0.0
            line_pledge = qty * unit_pledge
            if line_pledge <= 0:
                continue
            total_pledge_amount += line_pledge
            total_pledge_qty += qty
            pledge_product_ids.append(line.product_id.id)
        return total_pledge_amount, list(set(pledge_product_ids)), total_pledge_qty

    def _get_pledge_totals(self):
        """Pledge from remaining lines, or from snapshot when lines were stripped at sync.

        For **one** pledge product on the order, posted accounting uses **pledge_product_qty ×
        product.pledge_amount** (e.g. 5 × 10 → 50 on the journal entry), not a per-unit-only amount.
        Multiple pledge SKUs still use **total_pledge_amount** from the POS snapshot (sum of lines).
        """
        self.ensure_one()
        amt, pids, qty = self._compute_pledge_from_lines()
        _logger.info(
            "[PLEDGE][TRACE] _get_pledge_totals order=%s from_lines amount=%s qty=%s products=%s",
            self.name,
            amt,
            qty,
            pids,
        )
        if amt > 0:
            return amt, pids, qty
        pids_snap = list(self.pledge_snapshot_product_ids.ids)
        qty_snap = float(self.pledge_product_qty or 0)
        cur = self.currency_id or self.company_id.currency_id
        _logger.info(
            "[PLEDGE][TRACE] _get_pledge_totals order=%s snapshot amount=%s qty=%s products=%s",
            self.name,
            self.total_pledge_amount or 0.0,
            qty_snap,
            pids_snap,
        )
        if len(pids_snap) == 1 and qty_snap > 0:
            unit = float(self.env["product.product"].browse(pids_snap[0]).pledge_amount or 0.0)
            if unit > 0:
                je_amt = cur.round(qty_snap * unit)
                if je_amt > 0:
                    return je_amt, pids_snap, qty_snap
        snap_amt = self.total_pledge_amount or 0.0
        if snap_amt <= 0:
            return 0.0, [], 0.0
        return snap_amt, pids_snap, qty_snap

    @api.model
    def _pledge_strip_ui_order(self, order):
        """Compute pledge snapshot from UI payload without removing order lines.

        Previous behavior stripped pledged products from ``order['lines']`` and reduced payments.
        Business now requires pledged products to remain visible in ``pos.order`` lines
        with their natural sale price.
        """
        Product = self.env["product.product"].sudo()
        meta = {"total": 0.0, "product_ids": [], "qty": 0.0}
        is_refund = order.get("is_refund") or (order.get("amount_total") or 0) < 0
        if is_refund:
            return meta

        session = self.env["pos.session"].browse(order.get("session_id"))
        currency = session.currency_id if session.exists() else self.env.company.currency_id

        lines = order.get("lines") or []
        for index, line in enumerate(lines, start=1):
            if not isinstance(line, (list, tuple)) or len(line) < 3:
                continue
            vals = line[2]
            if not isinstance(vals, dict):
                continue
            pid = vals.get("product_id")
            if not pid:
                continue
            prod = Product.browse(pid)
            if prod.exists() and prod.has_pledge:
                qty = self._pledge_sync_line_qty(vals)
                line_pledge = 0.0
                # Prefer canonical pledge definition first.
                if qty > 0:
                    unit_pledge = float(prod.pledge_amount or 0.0)
                    if unit_pledge > 0:
                        line_pledge = currency.round(qty * unit_pledge)
                # Fallback for legacy data where pledge_amount is not configured.
                if line_pledge <= 0:
                    for key in ("price_subtotal_incl", "price_subtotal"):
                        raw = vals.get(key)
                        if raw is not None:
                            try:
                                cand = float(raw)
                            except (TypeError, ValueError):
                                cand = 0.0
                            if cand > 0:
                                line_pledge = cand
                                break
                if line_pledge > 0:
                    meta["total"] += line_pledge
                    meta["qty"] += qty
                    meta["product_ids"].append(pid)
                    _logger.info(
                        "[PLEDGE][TRACE] payload line %s keeps pledged product id=%s qty=%s sale_subtotal=%s pledge_snapshot=%s",
                        index,
                        pid,
                        qty,
                        vals.get("price_subtotal_incl", vals.get("price_subtotal")),
                        line_pledge,
                    )
                continue

        if meta["total"] <= 0:
            return meta

        meta["product_ids"] = list(set(meta["product_ids"]))
        meta["total"] = currency.round(meta["total"])
        _logger.info(
            "[PLEDGE][TRACE] pledge snapshot computed without stripping lines: total=%s qty=%s products=%s",
            meta["total"],
            meta["qty"],
            meta["product_ids"],
        )
        return meta

    @api.model
    def _pledge_recompute_sync_order_amounts(self, order):
        """Recompute pos.order header amounts from sync payload after pledge lines/payments were adjusted.

        Core _process_order passes the dict straight into create(); required monetary fields must be set.
        """
        sid = order.get("session_id")
        if not sid:
            return
        session = self.env["pos.session"].browse(sid)
        if not session.exists():
            return
        config = session.config_id
        vals_for_new = {
            "session_id": session.id,
            "company_id": order.get("company_id") or config.company_id.id,
            "pricelist_id": order.get("pricelist_id") or config.pricelist_id.id,
            "fiscal_position_id": order.get("fiscal_position_id")
            or config.default_fiscal_position_id.id,
            "lines": order.get("lines") or [],
            "payment_ids": order.get("payment_ids") or [],
            "is_refund": order.get("is_refund", False),
        }
        if order.get("partner_id"):
            vals_for_new["partner_id"] = order["partner_id"]
        stub = self.new(vals_for_new)
        stub._compute_prices()
        order["amount_tax"] = stub.amount_tax
        order["amount_total"] = stub.amount_total
        order["amount_paid"] = stub.amount_paid
        order["amount_return"] = stub.amount_return
        order["amount_difference"] = stub.amount_difference

    @api.model
    def _process_order(self, order, existing_order):
        pledge_meta = self._pledge_strip_ui_order(order)
        pos_order = self
        if pledge_meta["total"] > 0:
            pos_order = self.with_context(pos_pledge_sync=True)
        res_id = super(PosOrder, pos_order)._process_order(order, existing_order)
        po = self.browse(res_id).sudo()
        _logger.warning(
            "[PLEDGE][TRACE] _process_order done order=%s lines=%s pledge_lines=%s snapshot_total=%s",
            po.name,
            len(po.lines),
            len(po.lines.filtered(lambda l: l.product_id.has_pledge)),
            pledge_meta["total"],
        )
        if pledge_meta["total"] > 0:
            po.write({
                "total_pledge_amount": pledge_meta["total"],
                "pledge_product_qty": int(pledge_meta["qty"]),
                "pledge_snapshot_product_ids": [(6, 0, pledge_meta["product_ids"])],
            })
            # Journal entry & pos.pledge need snapshot + paid state. Core calls write({'state': paid})
            # before this snapshot exists, so _get_pledge_totals() was 0 in write() — run again here.
            if po.state in ("paid", "done", "invoiced"):
                po._create_pledge_collection_orders()
            else:
                _logger.warning(
                    "[PLEDGE][TRACE] _process_order skip immediate create order=%s state=%s",
                    po.name,
                    po.state,
                )
        return res_id

    def _process_payment_lines(self, order_data, order, pos_session, draft):
        """Sync amount_total/amount_paid from DB lines+payments; stub new() can diverge from persisted lines."""
        if self.env.context.get('pos_pledge_sync'):
            order._compute_prices()
        return super()._process_payment_lines(order_data, order, pos_session, draft)

    def _prepare_pos_pledge_tracking_vals(self, pledge_total, pledge_product_ids):
        """Prepare payload to create pos.pledge tracking record from a paid POS order."""
        self.ensure_one()
        employee_amount = 0.0
        delivery_amount = 0.0
        employee_product_id = False
        delivery_product_id = False

        for line in self.lines.filtered(lambda l: l.product_id):
            product = line.product_id
            if product.is_employee_service:
                employee_amount += line.price_subtotal_incl
                if not employee_product_id:
                    employee_product_id = product.id
            elif product.is_delivery_product:
                delivery_amount += line.price_subtotal_incl
                if not delivery_product_id:
                    delivery_product_id = product.id

        has_pledge = pledge_total > 0
        has_employee = employee_amount > 0
        has_delivery = delivery_amount > 0

        if has_employee and not has_pledge and not has_delivery:
            case_type = "case1"
        elif has_pledge and not has_delivery and not has_employee:
            case_type = "case2"
        elif has_pledge and has_delivery and not has_employee:
            case_type = "case3"
        elif has_pledge and has_employee and has_delivery:
            case_type = "case4"
        elif has_pledge and has_employee and not has_delivery:
            case_type = "case5"
        elif has_employee and has_delivery and not has_pledge:
            case_type = "case6"
        else:
            case_type = "mixed"

        return {
            "pos_order_id": self.id,
            "pos_config_id": self.config_id.id,
            "partner_id": self.partner_id.id,
            "employee_id": self.employee_id.id if self.employee_id else False,
            "case_type": case_type,
            "pledge_amount": pledge_total,
            "employee_amount": employee_amount,
            "delivery_amount": delivery_amount,
            "pledge_products": [(6, 0, pledge_product_ids or [])],
            "employee_product_id": employee_product_id,
            "delivery_product_id": delivery_product_id,
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id or self.company_id.currency_id.id,
        }

    def _pledge_get_payment_journal_from_order(self):
        self.ensure_one()
        for pay in self.payment_ids:
            if pay.payment_method_id and pay.payment_method_id.journal_id:
                return pay.payment_method_id.journal_id
        pm = self.config_id.payment_method_ids.filtered(lambda m: m.type == "cash" and m.journal_id)[:1]
        if pm:
            return pm.journal_id
        pm = self.config_id.payment_method_ids.filtered(lambda m: m.journal_id)[:1]
        return pm.journal_id

    def _pledge_get_inbound_payment_method_line(self, journal):
        line = journal.inbound_payment_method_line_ids.filtered(lambda l: l.payment_account_id)[:1]
        if not line:
            line = journal.inbound_payment_method_line_ids[:1]
        if not line:
            raise UserError(
                _("Please define an inbound payment method on journal %s for pledge deposit posting.")
                % journal.display_name
            )
        return line

    def _post_pledge_deposit_move(self):
        """Dr liquidity (same journal as POS payments) / Cr pledge liability — pledge not in pos.payment totals."""
        self.ensure_one()
        if self.pledge_deposit_move_id:
            return self.pledge_deposit_move_id

        pledge_total, _pids, pledge_qty = self._get_pledge_totals()
        if pledge_total <= 0 or pledge_qty <= 0:
            return self.env["account.move"]

        prec = self.currency_id.rounding
        if float_compare(pledge_total, self.total_pledge_amount or 0.0, precision_rounding=prec) != 0:
            self.sudo().write({"total_pledge_amount": pledge_total})

        liability_acc = self.config_id.pos_pledge_liability_account_id
        if not liability_acc:
            raise UserError(_("Please set 'Pledge Liability Account' on the POS configuration first."))
        if not self.partner_id:
            raise UserError(_("A customer is required to post pledge deposit for order %s.") % self.name)

        journal = self._pledge_get_payment_journal_from_order()
        if not journal:
            raise UserError(_("Configure payment methods with journals on the POS to post pledge deposits."))

        payment_method_line = self._pledge_get_inbound_payment_method_line(journal)
        liquidity_account = payment_method_line.payment_account_id
        if not liquidity_account:
            raise UserError(
                _(
                    "Configure an inbound payment method with a payment account on journal '%s' "
                    "so pledge deposits can be posted."
                )
                % journal.display_name
            )

        move = self.env["account.move"].sudo().create({
            "move_type": "entry",
            "journal_id": journal.id,
            "date": fields.Date.context_today(self),
            "ref": _("POS pledge deposit - %s") % self.name,
            "partner_id": self.partner_id.id,
            "line_ids": [
                Command.create({
                    "name": _("Pledge deposit %s") % self.name,
                    "account_id": liquidity_account.id,
                    "partner_id": self.partner_id.id,
                    "debit": pledge_total,
                    "credit": 0.0,
                }),
                Command.create({
                    "name": _("Pledge deposit %s") % self.name,
                    "account_id": liability_acc.id,
                    "partner_id": self.partner_id.id,
                    "debit": 0.0,
                    "credit": pledge_total,
                }),
            ],
        })
        move.action_post()
        self.pledge_deposit_move_id = move.id
        if self.session_id:
            self.session_id._invalidate_open_sessions_cash_balance()
        _logger.info(
            "[PLEDGE] Posted pledge deposit move %s for order %s (amount=%s)",
            move.id,
            self.name,
            pledge_total,
        )
        return move

    def _create_pledge_collection_orders(self):
        """On paid orders with pledge lines: post liability move and tracking record (no extra POS order)."""
        for order in self:
            _logger.info(
                "[PLEDGE][TRACE] _create_pledge_collection_orders order=%s state=%s partner=%s is_pledge_generated=%s",
                order.name,
                order.state,
                order.partner_id.id if order.partner_id else False,
                order.is_pledge_generated,
            )
            if order.is_pledge_generated:
                _logger.info(
                    "[PLEDGE][TRACE] skip order=%s reason=is_pledge_generated",
                    order.name,
                )
                continue
            pledge_total, pledge_product_ids, pledge_qty = order._get_pledge_totals()
            _logger.info(
                "[PLEDGE][TRACE] order=%s totals pledge_total=%s pledge_qty=%s pledge_product_ids=%s",
                order.name,
                pledge_total,
                pledge_qty,
                pledge_product_ids,
            )
            if pledge_total <= 0 or pledge_qty <= 0:
                _logger.info(
                    "[PLEDGE][TRACE] skip order=%s reason=pledge_total_or_qty_non_positive",
                    order.name,
                )
                continue

            if not order.partner_id:
                _logger.warning(
                    "[PLEDGE] Cannot process pledge for %s because customer is missing.",
                    order.name,
                )
                _logger.info(
                    "[PLEDGE][TRACE] skip order=%s reason=missing_partner",
                    order.name,
                )
                continue

            pledge_record = self.env["pos.pledge"].sudo().search([("pos_order_id", "=", order.id)], limit=1)
            _logger.info(
                "[PLEDGE][TRACE] existing pos.pledge lookup order=%s order_id=%s found=%s",
                order.name,
                order.id,
                pledge_record.id if pledge_record else False,
            )
            if not pledge_record:
                try:
                    vals = order._prepare_pos_pledge_tracking_vals(pledge_total, pledge_product_ids)
                    _logger.info(
                        "[PLEDGE][TRACE] creating pos.pledge for order=%s with vals=%s",
                        order.name,
                        vals,
                    )
                    pledge_record = self.env["pos.pledge"].sudo().create(vals)
                    _logger.info(
                        "[PLEDGE] Created pos.pledge %s for order %s",
                        pledge_record.name,
                        order.name,
                    )
                except Exception as e:
                    _logger.warning(
                        "[PLEDGE] Could not create pos.pledge from source order %s: %s",
                        order.name,
                        e,
                    )
                    _logger.exception(
                        "[PLEDGE][TRACE] create pos.pledge failed for order=%s",
                        order.name,
                    )
                    continue

            order.pledge_id = pledge_record.id
            _logger.info(
                "[PLEDGE][TRACE] linked order=%s to pledge_id=%s",
                order.name,
                pledge_record.id,
            )

            move = order._post_pledge_deposit_move()
            if move and pledge_record:
                pledge_record.pledge_move_id = move.id
                _logger.info(
                    "[PLEDGE][TRACE] linked pledge_id=%s to move_id=%s",
                    pledge_record.id,
                    move.id,
                )

    def write(self, vals):
        """Override write to trigger pledge order creation when order state changes."""
        _logger.warning("[PLEDGE] write() called on %d orders with vals: %s", len(self), vals)
        
        result = super().write(vals)
        
        # Pledge deposit is finalized in _process_order after total_pledge_amount snapshot write.
        # This hook still runs when state→paid before snapshot (early no-op) or for non-POS writes.
        if vals.get('state') in ('paid', 'done', 'invoiced'):
            _logger.warning("[PLEDGE] Order state changed to %s, checking for pledge orders", vals.get('state'))
            normal_orders = self.filtered(lambda o: not o.is_pledge_generated)
            normal_orders._create_pledge_collection_orders()
        else:
            _logger.warning("[PLEDGE][TRACE] write skip: state not in (paid, done, invoiced): %s", vals.get('state'))
        
        return result

    def _get_pos_payment_method_from_journal(self, journal, pos_config):
        """
        Get or create pos.payment.method from account.journal
        For cash journals, must create a new payment method for each POS config (cannot be shared)
        For bank journals, can be shared between configs
        """
        is_cash = journal.type == 'cash'
        
        # Check if there's an open session
        opened_session = pos_config.session_ids.filtered(lambda s: s.state != 'closed')
        has_open_session = bool(opened_session)
        
        # First, search in payment_method_ids of the config (already available)
        pos_payment_method = pos_config.payment_method_ids.filtered(
            lambda pm: pm.journal_id.id == journal.id
        )[:1]
        
        if pos_payment_method:
            # Payment method already in config - use it
            return pos_payment_method
        
        # If not found in config, search more broadly (anywhere)
        # Search for any payment method with this journal
        pos_payment_method = self.env['pos.payment.method'].search([
            ('journal_id', '=', journal.id),
        ], limit=1)
        
        if pos_payment_method:
            # Found a payment method - add it to config if not already there
            if pos_payment_method not in pos_config.payment_method_ids:
                # Use bypass context to allow modification even with open session
                try:
                    pos_config.with_context(bypass_payment_method_ids_forbidden_change=True).write({
                        'payment_method_ids': [(4, pos_payment_method.id)],
                    })
                except Exception:
                    # If still fails, try to add to config_ids only (might work)
                    if pos_config.id not in pos_payment_method.config_ids.ids:
                        pos_payment_method.write({
                            'config_ids': [(4, pos_config.id)],
                        })
            return pos_payment_method
        
        # If not found anywhere, create new one
        if is_cash:
            # For cash journals, search only in this config (cash cannot be shared)
            pos_payment_method = self.env['pos.payment.method'].search([
                ('journal_id', '=', journal.id),
                ('config_ids', 'in', [pos_config.id]),
            ], limit=1)
            
            # For cash, check if journal is already used by another payment method in another config
            if pos_payment_method:
                other_configs = self.env['pos.config'].search([
                    ('payment_method_ids', 'in', [pos_payment_method.id]),
                    ('id', '!=', pos_config.id),
                ])
                if other_configs:
                    # Journal is already used in another config - cannot reuse for cash
                    raise ValidationError(_(
                        'The cash journal "%s" is already used in another POS configuration. '
                        'Please configure a different cash journal for this POS configuration, '
                        'or remove it from the other configuration first.'
                    ) % journal.name)
            
            if not pos_payment_method:
                # Create a new payment method for this config
                pos_payment_method = self.env['pos.payment.method'].sudo().create({
                    'name': journal.name,
                    'journal_id': journal.id,
                    'config_ids': [(4, pos_config.id)],
                    'company_id': pos_config.company_id.id,
                })
                # Add to payment_method_ids using bypass context
                try:
                    pos_config.with_context(bypass_payment_method_ids_forbidden_change=True).write({
                        'payment_method_ids': [(4, pos_payment_method.id)],
                    })
                except Exception:
                    # If still fails, at least add to config_ids
                    pass
        else:
            # For bank journals, can be shared between configs
            if not pos_payment_method:
                # Create a new pos.payment.method if not found
                pos_payment_method = self.env['pos.payment.method'].sudo().create({
                    'name': journal.name,
                    'journal_id': journal.id,
                    'config_ids': [(4, pos_config.id)],
                    'company_id': pos_config.company_id.id,
                })
                # Add to payment_method_ids using bypass context
                try:
                    pos_config.with_context(bypass_payment_method_ids_forbidden_change=True).write({
                        'payment_method_ids': [(4, pos_payment_method.id)],
                    })
                except Exception:
                    # If still fails, at least add to config_ids
                    pass
        
        return pos_payment_method

    def _create_independent_payment(self, order, amount, journal, description):
        """
        Create an independent payment record for pledge/employee/delivery
        This payment is NOT linked to any invoice
        
        :param order: pos.order record
        :param amount: Amount for the payment
        :param journal: Journal to use
        :param description: Description for the payment
        :return: account.payment record or False
        """
        _logger.info("[PLEDGE] _create_independent_payment called:")
        _logger.info("[PLEDGE]   - Order: %s", order.name)
        _logger.info("[PLEDGE]   - Amount: %.2f", amount)
        _logger.info("[PLEDGE]   - Journal: %s", journal.name)
        _logger.info("[PLEDGE]   - Description: %s", description)
        
        if amount <= 0:
            _logger.warning("[PLEDGE] Amount is <= 0, returning False")
            return False
        
        if not order.partner_id:
            _logger.error("[PLEDGE] No partner found for %s payment", description)
            return False
        
        _logger.info("[PLEDGE] Partner: %s (ID: %s)", order.partner_id.name, order.partner_id.id)
        _logger.info("[PLEDGE] Currency: %s", order.currency_id.name if order.currency_id else order.company_id.currency_id.name)
        _logger.info("[PLEDGE] Date: %s", order.date_order)
        
        # Check for payment method
        if not journal.inbound_payment_method_line_ids:
            _logger.error("[PLEDGE] Journal %s has no inbound payment methods!", journal.name)
            return False
        
        payment_method = journal.inbound_payment_method_line_ids[0]
        _logger.info("[PLEDGE] Payment method: %s (ID: %s)", payment_method.name, payment_method.id)
        
        # Get pos.payment.method
        pos_config = order.config_id
        pos_payment_method = order._get_pos_payment_method_from_journal(journal, pos_config)
        
        try:
            # Create account.payment for accounting
            payment_vals = {
                'payment_type': 'inbound',  # Customer pays us
                'partner_type': 'customer',
                'partner_id': order.partner_id.id,
                'amount': amount,
                'currency_id': order.currency_id.id or order.company_id.currency_id.id,
                'journal_id': journal.id,
                'date': order.date_order,
                'memo': f"{order.name} - {description}",
                'payment_method_line_id': payment_method.id,
                # Do NOT set invoice_ids or reconciled_invoice_ids - this payment is independent
            }
            
            _logger.info("[PLEDGE] Creating account.payment record...")
            payment = self.env['account.payment'].create(payment_vals)
            _logger.info("[PLEDGE] ✓ Created independent account.payment for %s: %.2f (ID: %s, Name: %s)", 
                        description, amount, payment.id, payment.name)
            
            # POST the payment immediately
            _logger.info("[PLEDGE] Posting payment %s...", payment.name)
            payment.action_post()
            _logger.info("[PLEDGE] ✓ Payment %s posted successfully", payment.name)
            
            # Create pos.payment
            pos_payment = self.env['pos.payment'].sudo().create({
                'pos_order_id': order.id,
                'payment_method_id': pos_payment_method.id,
                'amount': amount,
                'payment_date': fields.Datetime.now(),
            })
            _logger.info("[PLEDGE] ✓ Created pos.payment for %s: %.2f (ID: %s)", 
                        description, amount, pos_payment.id)

            # Store reference in pos.pledge for tracking
            _logger.info("[PLEDGE] Searching for pos.pledge record with pos_order_id=%s", order.id)
            pledge_record = self.env['pos.pledge'].search([
                ('pos_order_id', '=', order.id)
            ], limit=1)

            if pledge_record:
                _logger.info("[PLEDGE] Found pledge record: %s (ID: %s)", pledge_record.name, pledge_record.id)
                if description == 'Pledge':
                    pledge_record.write({'pledge_payment_id': payment.id})
                    _logger.info("[PLEDGE] ✓ Linked pledge payment %s to pledge record %s", 
                                payment.name, pledge_record.name)
                elif description == 'Employee Service':
                    pledge_record.write({'employee_payment_id': payment.id})
                    _logger.info("[PLEDGE] ✓ Linked employee payment %s to pledge record %s", 
                                payment.name, pledge_record.name)
            else:
                _logger.warning("[PLEDGE] ⚠️ No pos.pledge record found for order %s - cannot link payment", order.name)
            
            return payment
        except Exception as e:
            _logger.error("[PLEDGE] ✗ Failed to create payment for %s: %s", description, str(e))
            import traceback
            _logger.error("[PLEDGE] Traceback: %s", traceback.format_exc())
            return False

    def action_pos_order_invoice(self):
        """
        Create invoices normally - pledge products appear with their product price
        Virtual pledge amounts are ONLY on receipts, NOT in invoices
        """
        _logger.info("[PLEDGE] Creating invoice - pledge products included with product price only")
        # Create invoice normally - no filtering of pledge products
        return super(PosOrder, self).action_pos_order_invoice()

    def _prepare_invoice_vals(self):
        """Override to exclude pledge/employee/delivery products from invoice"""
        vals = super()._prepare_invoice_vals()
        return vals

    def _prepare_invoice_lines(self, move_type):
        """
        Override to filter out pledge/employee/delivery products from invoice lines
        We override the entire method to have full control over line creation
        """
        invoice_lines = []
        excluded_count = 0
        
        for order in self:
            line_values_list = order.with_context(invoicing=True)._prepare_tax_base_line_values()
            
            for line_values in line_values_list:
                line = line_values['record']
                product = line.product_id
                
                # Skip employee service products
                if product.is_employee_service:
                    _logger.info("[PLEDGE] Excluding employee service product '%s' from invoice", product.display_name)
                    excluded_count += 1
                    continue
                
                # Skip delivery products
                if product.is_delivery_product:
                    _logger.info("[PLEDGE] Excluding delivery product '%s' from invoice", product.display_name)
                    excluded_count += 1
                    continue
                
                # Include all other products (including pledge products at product price only)
                # Virtual pledge amounts are ONLY on receipts, NOT in invoices
                
                # Get invoice line values
                invoice_lines_values = order._get_invoice_lines_values(line_values, line, move_type)
                if invoice_lines_values:  # Only add if not empty
                    invoice_lines.append((0, None, invoice_lines_values))
                
                # Add price discount note if applicable
                is_percentage = order.pricelist_id and any(
                    order.pricelist_id.item_ids.filtered(
                        lambda rule: rule.compute_price == "percentage")
                )
                if is_percentage and self.env['decimal.precision'].precision_get('Product Price'):
                    precision = self.env['decimal.precision'].precision_get('Product Price')
                    if float_compare(line.price_unit, line.product_id.lst_price, precision_digits=precision) < 0:
                        invoice_lines.append((0, None, {
                            'name': _('Price discount from %(original_price)s to %(discounted_price)s',
                                    original_price=float_repr(line.product_id.lst_price, order.currency_id.decimal_places),
                                    discounted_price=float_repr(line.price_unit, order.currency_id.decimal_places)),
                            'display_type': 'line_note',
                        }))
                
                # Add customer note if applicable
                if line.customer_note:
                    invoice_lines.append((0, None, {
                        'name': line.customer_note,
                        'display_type': 'line_note',
                    }))
            
            # Add general customer note
            if order.general_customer_note:
                invoice_lines.append((0, None, {
                    'name': order.general_customer_note,
                    'display_type': 'line_note',
                }))
        
        _logger.info(
            "[PLEDGE] Invoice lines prepared: %d lines (excluded %d employee/delivery products)",
            len(invoice_lines), excluded_count
        )
        
        return invoice_lines

    def _get_invoice_lines_to_invoice(self):
        """
        Filter out pledge, employee, and delivery products from invoice
        This ensures invoices only contain regular products
        """
        lines = super()._get_invoice_lines_to_invoice()
        
        # Exclude pledge products
        filtered_lines = lines.filtered(
            lambda l: not l.product_id.has_pledge
        )
        
        _logger.info(
            "[PLEDGE] Filtered invoice lines: %d regular items (excluded %d pledge items)",
            len(filtered_lines),
            len(lines) - len(filtered_lines)
        )
        
        return filtered_lines


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    is_pledge_related = fields.Boolean(
        string='Pledge Related',
        compute='_compute_pledge_related',
        store=True
    )

    @api.depends('product_id.has_pledge')
    def _compute_pledge_related(self):
        for line in self:
            line.is_pledge_related = line.product_id.has_pledge
