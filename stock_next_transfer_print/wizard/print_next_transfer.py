from odoo import fields, models


class StockPrintNextTransferWizard(models.TransientModel):
    _name = "stock.print.next.transfer.wizard"
    _description = "Print Next Transfer"

    picking_id = fields.Many2one("stock.picking", required=True, readonly=True)
    line_ids = fields.One2many(
        "stock.print.next.transfer.wizard.line",
        "wizard_id",
        string="Next Transfers",
    )


class StockPrintNextTransferWizardLine(models.TransientModel):
    _name = "stock.print.next.transfer.wizard.line"
    _description = "Print Next Transfer Line"
    _order = "id"

    wizard_id = fields.Many2one(
        "stock.print.next.transfer.wizard",
        required=True,
        ondelete="cascade",
    )
    picking_id = fields.Many2one("stock.picking", required=True, readonly=True)
    picking_type_id = fields.Many2one(
        related="picking_id.picking_type_id",
        string="Operation Type",
    )
    state = fields.Selection(related="picking_id.state", string="Status")
    scheduled_date = fields.Datetime(related="picking_id.scheduled_date")

    def action_print(self):
        self.ensure_one()
        return self.picking_id.do_print_picking()
