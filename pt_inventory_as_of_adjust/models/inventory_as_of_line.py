# -*- coding: utf-8 -*-
import logging
import traceback

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero

_logger = logging.getLogger(__name__)


class InventoryAsOfLine(models.Model):
    _name = "inventory.as.of.line"
    _description = "As-of Inventory Adjustment Line"
    _order = "row_number, id"

    batch_id = fields.Many2one(
        "inventory.as.of.batch",
        required=True,
        ondelete="cascade",
        index=True,
    )
    row_number = fields.Integer(index=True)
    raw_sku = fields.Char(string="Product Key")
    product_id = fields.Many2one("product.product", string="Product", index=True)
    location_id = fields.Many2one(
        "stock.location",
        string="Location",
        required=True,
        domain="[('usage', 'in', ('internal', 'transit')), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        check_company=True,
    )
    counted_as_of = fields.Float(string="Counted As Of", digits="Product Unit")
    qty_as_of = fields.Float(
        string="On Hand As Of",
        digits="Product Unit",
        readonly=True,
    )
    qty_today = fields.Float(
        string="On Hand Today",
        digits="Product Unit",
        readonly=True,
    )
    correction = fields.Float(
        string="Correction",
        digits="Product Unit",
        readonly=True,
    )
    counted_to_apply = fields.Float(
        string="Counted To Apply",
        digits="Product Unit",
        readonly=True,
    )
    stock_move_id = fields.Many2one(
        "stock.move",
        string="Inventory Move",
        readonly=True,
        copy=False,
    )
    account_move_id = fields.Many2one(
        "account.move",
        string="Journal Entry",
        readonly=True,
        copy=False,
        index=True,
    )
    state = fields.Selection(
        selection=[
            ("to_apply", "To Apply"),
            ("skip", "Skip"),
            ("applied", "Applied"),
            ("error", "Error"),
        ],
        default="to_apply",
        required=True,
        index=True,
    )
    note = fields.Char(string="Valuation Note")
    error_message = fields.Text()
    company_id = fields.Many2one(related="batch_id.company_id", store=True)

    def write(self, vals):
        res = super().write(vals)
        if "counted_as_of" in vals or "location_id" in vals or "product_id" in vals:
            self._recompute_correction_fields()
        elif "state" in vals:
            # Keep skip/to_apply consistent when user toggles after editing qty.
            pass
        return res

    def _recompute_correction_fields(self):
        for line in self:
            if line.state == "applied":
                continue
            if not line.product_id or not line.location_id or not line.batch_id.as_of_datetime:
                continue
            product = line.product_id
            location = line.location_id
            company = line.batch_id.company_id
            qty_today = product.with_company(company).with_context(
                location=location.id,
                company_id=company.id,
            ).qty_available
            qty_as_of = product.with_company(company).with_context(
                location=location.id,
                company_id=company.id,
                to_date=line.batch_id.as_of_datetime,
            ).qty_available
            correction = line.counted_as_of - qty_as_of
            counted_to_apply = qty_today + correction
            rounding = product.uom_id.rounding
            new_state = line.state
            if line.state in ("to_apply", "skip", "error") and line.product_id:
                if float_is_zero(correction, precision_rounding=rounding):
                    new_state = "skip"
                elif line.state == "skip":
                    new_state = "to_apply"
                elif line.state == "error" and not line.error_message:
                    new_state = "to_apply"
            super(InventoryAsOfLine, line).write(
                {
                    "qty_as_of": qty_as_of,
                    "qty_today": qty_today,
                    "correction": correction,
                    "counted_to_apply": counted_to_apply,
                    "state": new_state,
                    "error_message": False if new_state != "error" else line.error_message,
                }
            )

    def action_mark_skip(self):
        self.filtered(lambda l: l.state in ("to_apply", "error")).write({"state": "skip"})

    def action_mark_to_apply(self):
        for line in self.filtered(lambda l: l.state in ("skip", "error")):
            if not line.product_id:
                continue
            rounding = line.product_id.uom_id.rounding
            if float_is_zero(line.correction, precision_rounding=rounding):
                continue
            line.write({"state": "to_apply", "error_message": False})

    def _get_or_prepare_quant(self, accounting_date):
        """Find/create the quant and set inventory_quantity for apply."""
        self.ensure_one()
        if not self.product_id or not self.location_id:
            raise UserError(_("Line %(row)s is missing product or location.") % {"row": self.row_number})

        company = self.company_id
        if self.location_id.company_id and self.location_id.company_id != company:
            raise UserError(
                _(
                    "Line %(row)s location %(location)s belongs to company %(loc_company)s, "
                    "but the batch company is %(batch_company)s."
                )
                % {
                    "row": self.row_number,
                    "location": self.location_id.complete_name,
                    "loc_company": self.location_id.company_id.display_name,
                    "batch_company": company.display_name,
                }
            )

        Quant = (
            self.env["stock.quant"]
            .with_company(company)
            .with_context(
                inventory_mode=True,
                allowed_company_ids=company.ids,
            )
            .sudo()
        )
        quant = Quant.search(
            [
                ("product_id", "=", self.product_id.id),
                ("location_id", "=", self.location_id.id),
                ("lot_id", "=", False),
                ("package_id", "=", False),
                ("owner_id", "=", False),
            ],
            limit=1,
        )
        if not quant:
            quant = Quant.create(
                {
                    "product_id": self.product_id.id,
                    "location_id": self.location_id.id,
                    "inventory_quantity": self.counted_to_apply,
                }
            )
        else:
            quant.inventory_quantity = self.counted_to_apply

        if accounting_date:
            quant.accounting_date = accounting_date
        quant.invalidate_recordset(["inventory_diff_quantity", "inventory_quantity_set"])
        return quant

    def _apply_inventory_adjustment(self, as_of_datetime, accounting_date, inventory_name):
        """Apply one line (wrapper). Prefer batch apply for a shared journal entry."""
        self.ensure_one()
        self._apply_inventory_adjustments(
            as_of_datetime=as_of_datetime,
            accounting_date=accounting_date,
            inventory_name=inventory_name,
        )

    def _apply_inventory_adjustments(self, as_of_datetime, accounting_date, inventory_name):
        """Apply lines together so Odoo creates one JE for many inventory stock moves.

        Same behavior as Physical Inventory "Apply" on multiple quants:
        separate stock.move per quant, one shared account.move.
        """
        lines = self.filtered(lambda l: l.state == "to_apply")
        if not lines:
            return

        prepared = {}  # line_id -> (quant, qty_before)
        for line in lines:
            try:
                quant = line._get_or_prepare_quant(accounting_date)
                prepared[line.id] = (quant, quant.quantity)
            except Exception as exc:
                _logger.exception(
                    "As-of inventory prepare failed for line %s", line.id
                )
                line.write(
                    {
                        "state": "error",
                        "error_message": "%s\n%s" % (exc, traceback.format_exc()),
                    }
                )

        ok_lines = lines.filtered(lambda l: l.id in prepared)
        if not ok_lines:
            return

        # Unique quants in stable order.
        quants = self.env["stock.quant"]
        seen = set()
        for line in ok_lines:
            quant = prepared[line.id][0]
            if quant.id not in seen:
                seen.add(quant.id)
                quants |= quant

        Move = self.env["stock.move"].sudo()
        last_move_id = Move.search([("is_inventory", "=", True)], order="id desc", limit=1).id or 0

        ctx = {
            "inventory_name": inventory_name,
            "force_period_date": accounting_date,
            "allowed_company_ids": ok_lines.mapped("company_id").ids,
        }
        # Use batch/line company so company-dependent Inventory Location
        # (property_stock_inventory) and category valuation accounts resolve correctly.
        company = ok_lines[:1].company_id
        apply_quants = quants.with_company(company).with_context(**ctx)
        try:
            # Pass date positionally AND as both known kw names for inherited overrides.
            try:
                apply_quants._apply_inventory(as_of_datetime)
            except TypeError:
                apply_quants._apply_inventory(date=as_of_datetime)
        except Exception as exc:
            _logger.exception(
                "As-of inventory batch apply failed for lines %s", ok_lines.ids
            )
            ok_lines.write(
                {
                    "state": "error",
                    "error_message": "%s\n%s" % (exc, traceback.format_exc()),
                }
            )
            return

        new_moves = Move.search(
            [("is_inventory", "=", True), ("id", ">", last_move_id)],
            order="id asc",
        )
        # Ensure backdated move date (some _apply_inventory overrides drop the date arg).
        if as_of_datetime and new_moves:
            new_moves.write({"date": as_of_datetime})
            new_moves.move_line_ids.write({"date": as_of_datetime})
        # All moves from one _action_done share the same account.move when JE is created.
        shared_account_move = new_moves.mapped("account_move_id")[:1]

        with_je = 0
        without_je = 0
        for line in ok_lines:
            quant, qty_before = prepared[line.id]
            stock_move = new_moves.filtered(
                lambda m, loc=line.location_id, product=line.product_id: m.product_id == product
                and (m.location_id == loc or m.location_dest_id == loc)
            )[:1]
            if not stock_move and len(ok_lines) == 1 and len(new_moves) == 1:
                stock_move = new_moves
            account_move = (
                stock_move.account_move_id
                if stock_move and stock_move.account_move_id
                else shared_account_move
            )
            diag = line._diagnose_valuation_journal(
                stock_move=stock_move,
                accounting_date=accounting_date,
                quant_qty_before=qty_before,
                counted_to_apply=line.counted_to_apply,
            )
            reason = line._journal_skip_reason(stock_move)
            if account_move:
                with_je += 1
                _logger.info(
                    "As-of JE OK | line=%s batch=%s product=%s [%s] location=%s "
                    "stock_move=%s account_move=%s | %s",
                    line.id,
                    line.batch_id.id,
                    line.product_id.default_code or line.product_id.id,
                    line.product_id.display_name,
                    line.location_id.complete_name,
                    stock_move.id if stock_move else False,
                    account_move.id,
                    diag,
                )
            else:
                without_je += 1
                _logger.warning(
                    "As-of JE MISSING | reason=%s | line=%s batch=%s product=%s [%s] "
                    "location=%s correction=%s stock_move=%s | %s",
                    reason,
                    line.id,
                    line.batch_id.id,
                    line.product_id.default_code or line.product_id.id,
                    line.product_id.display_name,
                    line.location_id.complete_name,
                    line.correction,
                    stock_move.id if stock_move else False,
                    diag,
                )
            line.write(
                {
                    "state": "applied",
                    "error_message": False,
                    "note": diag,
                    "stock_move_id": stock_move.id if stock_move else False,
                    "account_move_id": account_move.id if account_move else False,
                }
            )

        _logger.info(
            "As-of inventory apply done | batch_lines=%s new_stock_moves=%s "
            "shared_account_move=%s with_je=%s without_je=%s accounting_date=%s",
            len(ok_lines),
            len(new_moves),
            shared_account_move.id if shared_account_move else False,
            with_je,
            without_je,
            accounting_date,
        )

    def action_open_account_move(self):
        self.ensure_one()
        if not self.account_move_id:
            raise UserError(
                _("No journal entry linked to this line.\n%(note)s")
                % {"note": self.note or ""}
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Journal Entry"),
            "res_model": "account.move",
            "res_id": self.account_move_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_stock_move(self):
        self.ensure_one()
        if not self.stock_move_id:
            raise UserError(_("No inventory stock move linked to this line."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Inventory Move"),
            "res_model": "stock.move",
            "res_id": self.stock_move_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def _find_inventory_stock_move(self, as_of_datetime, inventory_name, after_move_id=0):
        self.ensure_one()
        Move = self.env["stock.move"].sudo()
        loc = self.location_id
        base = [
            ("product_id", "=", self.product_id.id),
            ("is_inventory", "=", True),
            ("state", "=", "done"),
            "|",
            ("location_id", "=", loc.id),
            ("location_dest_id", "=", loc.id),
        ]
        if after_move_id:
            move = Move.search(base + [("id", ">", after_move_id)], order="id desc", limit=1)
            if move:
                return move

        # Fallbacks: exact date+reason, then latest inventory move on location.
        moves = Move.search(
            base
            + [
                ("date", "=", as_of_datetime),
                "|",
                ("reference", "=", inventory_name),
                ("inventory_name", "=", inventory_name),
            ],
            order="id desc",
            limit=1,
        )
        if moves:
            return moves
        return Move.search(base, order="id desc", limit=1)

    def _journal_skip_reason(self, stock_move):
        """Short machine-readable reason when no account.move was created."""
        self.ensure_one()
        product = self.product_id
        if not stock_move:
            return "no_stock_move"
        if stock_move.account_move_id:
            return "ok"
        valuation = product.with_company(self.company_id).valuation
        src_acc = stock_move.location_id.with_company(self.company_id).valuation_account_id
        dest_acc = stock_move.location_dest_id.with_company(self.company_id).valuation_account_id
        if not product.is_storable:
            return "product_not_storable"
        if not (src_acc or dest_acc):
            return "missing_location_valuation_account"
        if valuation != "real_time":
            return "valuation_not_real_time(%s)" % valuation
        if not stock_move.is_valued:
            return "move_not_valued"
        if float_is_zero(stock_move.quantity, precision_rounding=stock_move.product_uom.rounding):
            return "zero_quantity"
        try:
            if not stock_move._should_create_account_move():
                return "should_create_account_move_false"
        except Exception as exc:
            return "should_create_error(%s)" % exc
        return "should_create_true_but_no_account_move_linked"

    def _diagnose_valuation_journal(
        self, stock_move, accounting_date, quant_qty_before=None, counted_to_apply=None
    ):
        """Explain why an account.move was or was not created for this adjustment."""
        self.ensure_one()
        product = self.product_id
        if not stock_move:
            before = quant_qty_before
            target = counted_to_apply if counted_to_apply is not None else self.counted_to_apply
            if before is not None and float_is_zero(
                (target or 0.0) - before, precision_rounding=product.uom_id.rounding
            ):
                return _(
                    "No stock.move created: on-hand on this exact location quant "
                    "(%(before)s) already equals counted to apply (%(target)s). "
                    "Note: On Hand Today can include child locations, so it may differ."
                ) % {"before": before, "target": target}
            return _(
                "No inventory stock.move found after apply (product=%(product)s, "
                "location=%(location)s, quant_before=%(before)s, counted_to_apply=%(target)s)."
            ) % {
                "product": product.display_name,
                "location": self.location_id.complete_name,
                "before": before,
                "target": target,
            }

        move = stock_move
        valuation = product.with_company(self.company_id).valuation
        # Resolve Inventory Location / valuation accounts in the batch company.
        inv_loc = product.with_company(self.company_id).property_stock_inventory
        is_storable = bool(product.is_storable)
        is_valued = bool(move.is_valued)
        src_acc = move.location_id.with_company(self.company_id).valuation_account_id
        dest_acc = move.location_dest_id.with_company(self.company_id).valuation_account_id
        has_loc_valuation_acc = bool(src_acc or dest_acc)
        should_create = False
        should_create_error = False
        try:
            should_create = bool(move._should_create_account_move())
        except Exception as exc:
            should_create_error = str(exc)

        parts = [
            _("stock_move_id=%(id)s value=%(value)s account_move_id=%(am)s")
            % {
                "id": move.id,
                "value": move.value,
                "am": move.account_move_id.id if move.account_move_id else False,
            },
            _("src=%(src)s (valuation_account=%(acc)s)")
            % {
                "src": move.location_id.complete_name,
                "acc": src_acc.display_name if src_acc else False,
            },
            _("dest=%(dest)s (valuation_account=%(acc)s)")
            % {
                "dest": move.location_dest_id.complete_name,
                "acc": dest_acc.display_name if dest_acc else False,
            },
            _("product.valuation=%(val)s (need real_time)") % {"val": valuation},
            _("product.property_stock_inventory@%(company)s=%(loc)s")
            % {
                "company": self.company_id.display_name,
                "loc": inv_loc.complete_name if inv_loc else False,
            },
            _("is_storable=%(s)s is_valued=%(v)s has_location_valuation_account=%(h)s")
            % {"s": is_storable, "v": is_valued, "h": has_loc_valuation_acc},
            _("_should_create_account_move=%(r)s") % {"r": should_create},
            _("accounting_date_context=%(d)s") % {"d": accounting_date},
        ]
        if should_create_error:
            parts.append(_("should_create_error=%(e)s") % {"e": should_create_error})

        if move.account_move_id:
            parts.append(
                _("Journal entry created: %(name)s date=%(date)s state=%(state)s")
                % {
                    "name": move.account_move_id.display_name,
                    "date": move.account_move_id.date,
                    "state": move.account_move_id.state,
                }
            )
        elif not has_loc_valuation_acc:
            parts.append(
                _(
                    "NO journal: Inventory adjustment location has no Valuation Account. "
                    "In Odoo 19, stock.move only posts if src/dest has valuation_account_id. "
                    "Set it on Virtual Locations/Inventory adjustment, or use Inventory Valuation closing."
                )
            )
        elif valuation != "real_time":
            parts.append(
                _("NO journal: product valuation is %(val)s, not real_time.")
                % {"val": valuation}
            )
        elif not is_valued:
            parts.append(_("NO journal: stock.move.is_valued is False."))
        elif not should_create:
            parts.append(_("NO journal: _should_create_account_move returned False."))
        else:
            parts.append(
                _(
                    "NO journal linked even though should_create=True "
                    "(check stock journal / account move create)."
                )
            )
        return " | ".join(str(p) for p in parts)
