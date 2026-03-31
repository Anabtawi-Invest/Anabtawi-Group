import base64

from odoo import api, fields, models


class StockLocation(models.Model):
    _inherit = "stock.location"

    is_truck = fields.Boolean(string="Is Truck", default=False)

    discrepancy_ids = fields.One2many(
        "stock.transfer.discrepancy",
        "truck_location_id",
        string="Transfer Discrepancies",
        readonly=True,
    )

    has_open_discrepancy = fields.Boolean(
        string="Has Open Discrepancy",
        compute="_compute_has_open_discrepancy",
        store=True,
        readonly=True,
    )

    @api.depends("discrepancy_ids.state")
    def _compute_has_open_discrepancy(self):
        if not self.ids:
            for loc in self:
                loc.has_open_discrepancy = False
            return

        data = self.env["stock.transfer.discrepancy"]._read_group(
            [("truck_location_id", "in", self.ids), ("state", "=", "open")],
            ["truck_location_id"],
            ["__count"],
        )
        open_map = {truck.id: count for truck, count in data}
        for loc in self:
            loc.has_open_discrepancy = bool(open_map.get(loc.id))

    @api.depends("barcode")
    def _compute_barcode_img(self):
        """Graceful fallback when reportlab render backend is missing.

        enterprise/stock_barcode computes barcode PNGs on stock.location.
        On environments missing rlPyCairo/_rl_renderPM, we keep the field empty
        instead of crashing the whole view rendering.
        """
        if "barcode_img" not in self._fields:
            return

        options = {"width": 300, "height": 100, "humanreadable": True}
        for location in self:
            if not location.barcode:
                location.barcode_img = False
                continue
            try:
                barcode = self.env["ir.actions.report"].barcode("Code128", location.barcode, **options)
                location.barcode_img = base64.b64encode(barcode).decode()
            except Exception:
                location.barcode_img = False

