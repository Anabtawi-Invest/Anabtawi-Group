from datetime import timedelta

from odoo import fields, models, _
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = "stock.move"

    is_backdated = fields.Boolean(
        string="Backdated",
        copy=False,
        help="This stock move was posted using an Effective Date / Accounting Date instead of today.",
    )

    def _action_done(self, cancel_backorder=False):
        res = super()._action_done(cancel_backorder=cancel_backorder)
        force_date = self.env.context.get("force_period_date")
        force_dt = self.env.context.get("force_effective_datetime")
        if not force_date and not force_dt:
            return res

        # Pickings overwrite date_done=now() after this method. Let stock.picking finish it.
        if self.picking_id and not self.env.context.get("inventory_backdate_from_quant"):
            return res

        done_moves = self.filtered(lambda move: move.state == "done")
        if not done_moves:
            return res

        backdate_dt = force_dt or self.env["stock.quant"]._inventory_backdate_datetime(force_date)
        reason = self.env.context.get("inventory_backdate_reason") or ""
        done_moves._apply_inventory_backdate(backdate_dt, reason)
        return res

    def _apply_inventory_backdate(self, backdate_dt, reason=""):
        done_moves = self.filtered(lambda move: move.state == "done")
        if not done_moves or not backdate_dt:
            return
        done_moves.write({
            "date": backdate_dt,
            "is_backdated": True,
        })
        pickings = done_moves.picking_id
        if pickings:
            pickings.with_context(skip_backdate_valuation=True).write({"date_done": backdate_dt})
        done_moves._post_inventory_backdate_log(fields.Date.to_date(backdate_dt), reason)
        done_moves._sync_backdated_account_move_date(backdate_dt)
        done_moves._recompute_backdated_valuation()

    def _post_inventory_backdate_log(self, accounting_date, reason):
        body = _(
            "Inventory/transfer backdated.\nDate: %(date)s\nUser: %(user)s\nReason: %(reason)s",
            date=accounting_date,
            user=self.env.user.display_name,
            reason=reason or _("Not specified"),
        )
        for picking in self.picking_id:
            picking.message_post(body=body)
        for account_move in self.account_move_id:
            account_move.message_post(body=body)

    def _sync_backdated_account_move_date(self, backdate_dt):
        journal_date = fields.Date.to_date(backdate_dt)
        for account_move in self.account_move_id:
            if account_move.date == journal_date:
                continue
            try:
                account_move.sudo().write({"date": journal_date})
            except UserError:
                continue

    def _recompute_backdated_valuation(self):
        """Replay stored move values from the backdate so later movements stay consistent."""
        if self.env.context.get("skip_backdate_valuation"):
            return
        done_moves = self.filtered(lambda move: move.state == "done")
        if not done_moves:
            return

        company = done_moves.company_id[:1] or self.env.company
        min_date = min(done_moves.mapped("date"))
        backdated_ids = set(done_moves.ids)

        for product in done_moves.product_id:
            product = product.with_company(company)
            later_moves = self.env["stock.move"].search([
                ("product_id", "=", product.id),
                ("company_id", "=", company.id),
                ("state", "=", "done"),
                ("date", ">=", min_date),
                "|", "|",
                ("is_in", "=", True),
                ("is_out", "=", True),
                ("is_dropship", "=", True),
            ], order="date, id")
            if not later_moves:
                continue

            if product.cost_method == "standard":
                for move in later_moves.filtered(lambda m: m.id in backdated_ids and m.is_in):
                    move.value = move.sudo()._get_value(at_date=move.date)
                continue

            seed_date = min_date - timedelta(seconds=1)
            quantity = product.with_context(to_date=seed_date).qty_available
            if product.cost_method == "average" and hasattr(product, "_run_average_batch"):
                std_map = product._run_average_batch(at_date=seed_date)[0]
                average_cost = std_map.get(product.id) or 0.0
            else:
                average_cost = product.standard_price or 0.0
            value = average_cost * quantity

            for move in later_moves:
                qty = move._get_valued_qty()
                if not qty:
                    continue
                if move.is_in or move.is_dropship:
                    if move.id in backdated_ids:
                        in_value = move.sudo()._get_value(at_date=move.date)
                        move.value = in_value
                    else:
                        in_value = move.value
                    if quantity > 0:
                        value += in_value
                        quantity += qty
                        average_cost = value / quantity if quantity else average_cost
                    else:
                        quantity += qty
                        average_cost = (in_value / qty) if qty else average_cost
                        value = average_cost * quantity
                if move.is_out or move.is_dropship:
                    out_value = qty * average_cost
                    move.value = out_value
                    value -= out_value
                    quantity -= qty

            product._update_standard_price()
