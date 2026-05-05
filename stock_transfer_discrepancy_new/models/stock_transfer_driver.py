from odoo import api, fields, models


class StockTransferDriver(models.Model):
    _name = "stock.transfer.driver"
    _description = "Truck Driver"
    _rec_name = "employee_id"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        required=True,
        ondelete="restrict",
        index=True,
    )
    company_id = fields.Many2one(
        related="employee_id.company_id",
        store=True,
        readonly=True,
    )
    discrepancy_ids = fields.One2many(
        "stock.transfer.discrepancy",
        "driver_id",
        string="Transfer Discrepancies",
        readonly=True,
    )
    is_blocked = fields.Boolean(
        string="Blocked",
        compute="_compute_is_blocked",
        store=True,
        readonly=True,
    )

    _sql_constraints = [
        (
            "stock_transfer_driver_employee_unique",
            "UNIQUE(employee_id)",
            "This employee is already registered as a driver.",
        ),
    ]

    @api.depends("discrepancy_ids.state")
    def _compute_is_blocked(self):
        if not self.ids:
            for rec in self:
                rec.is_blocked = False
            return
        data = self.env["stock.transfer.discrepancy"]._read_group(
            [("driver_id", "in", self.ids), ("state", "=", "open")],
            ["driver_id"],
            ["__count"],
        )
        blocked_map = {drv.id: count for drv, count in data}
        for rec in self:
            rec.is_blocked = bool(blocked_map.get(rec.id))
