from odoo import _, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def action_print_next_transfer_operations(self):
        """Print Picking Operations for the transfer created from this one.

        One next transfer prints immediately. Several next transfers open a
        picker so the user chooses which report to print.
        """
        self.ensure_one()
        next_transfers = self._get_next_transfers()
        if not next_transfers:
            raise UserError(_("This transfer has no next transfer to print."))
        if len(next_transfers) == 1:
            return next_transfers.do_print_picking()
        wizard = self.env["stock.print.next.transfer.wizard"].create({
            "picking_id": self.id,
            "line_ids": [
                (0, 0, {"picking_id": picking.id})
                for picking in next_transfers
            ],
        })
        return {
            "name": _("Print Next Transfer"),
            "type": "ir.actions.act_window",
            "res_model": "stock.print.next.transfer.wizard",
            "view_mode": "form",
            "res_id": wizard.id,
            "target": "new",
        }
