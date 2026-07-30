from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    direct_sales_enabled = fields.Boolean(
        string="Enable Direct Sales Invoice",
        default=False,
    )
    direct_sales_dispatch_location_id = fields.Many2one(
        "stock.location",
        string="Direct Sales Dispatch Location",
        check_company=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [company_id, False])]",
    )
    direct_sales_approval_user_ids = fields.Many2many(
        "res.users",
        "stock_warehouse_direct_sales_approver_rel",
        "warehouse_id",
        "user_id",
        string="Warehouse Approvers",
        domain="[('company_ids', 'in', [company_id])]",
    )
    direct_sales_user_ids = fields.Many2many(
        "res.users",
        "stock_warehouse_direct_sales_user_rel",
        "warehouse_id",
        "user_id",
        string="Permitted Direct Sales Users",
        domain="[('company_ids', 'in', [company_id])]",
        help="Sales and warehouse users permitted to use or process this warehouse.",
    )
    direct_sales_operation_type_id = fields.Many2one(
        "stock.picking.type",
        string="Direct Sales Preparation Operation Type",
        check_company=True,
        domain="[('code', '=', 'internal'), ('warehouse_id', '=', id)]",
    )
    direct_sales_stock_flow = fields.Selection(
        [
            ("direct_delivery", "Direct Delivery"),
            ("dispatch_then_customer", "Dispatch then Customer"),
        ],
        string="Direct Sales Stock Flow",
        default=lambda self: self.env.company.direct_sales_stock_flow,
        required=True,
    )

    @api.constrains("direct_sales_dispatch_location_id", "view_location_id")
    def _check_direct_sales_dispatch_location(self):
        for warehouse in self:
            location = warehouse.direct_sales_dispatch_location_id
            if location and not warehouse._direct_sales_contains_location(location):
                raise ValidationError(
                    _(
                        "The direct sales dispatch location must belong to warehouse %s.",
                        warehouse.display_name,
                    )
                )

    def _direct_sales_contains_location(self, location):
        """Return whether ``location`` is inside this warehouse hierarchy."""
        self.ensure_one()
        if not location or not self.view_location_id:
            return False
        return bool(
            self.env["stock.location"]
            .sudo()
            .search_count(
                [
                    ("id", "=", location.id),
                    ("id", "child_of", self.view_location_id.id),
                ],
                limit=1,
            )
        )

    def _ensure_direct_sales_setup(self):
        """Create missing warehouse-local dispatch configuration safely and idempotently."""
        Location = self.env["stock.location"].sudo()
        PickingType = self.env["stock.picking.type"].sudo()
        for warehouse in self:
            updates = {}
            dispatch = warehouse.direct_sales_dispatch_location_id
            if not dispatch:
                company_default = (
                    warehouse.company_id.direct_sales_default_dispatch_location_id
                )
                if company_default and warehouse._direct_sales_contains_location(
                    company_default
                ):
                    dispatch = company_default
                    updates["direct_sales_dispatch_location_id"] = dispatch.id
            if not dispatch:
                dispatch = Location.search(
                    [
                        ("location_id", "=", warehouse.lot_stock_id.id),
                        ("name", "=", "Sales Dispatch"),
                        ("company_id", "in", [warehouse.company_id.id, False]),
                    ],
                    limit=1,
                )
                if not dispatch:
                    dispatch = Location.create(
                        {
                            "name": "Sales Dispatch",
                            "usage": "internal",
                            "location_id": warehouse.lot_stock_id.id,
                            "company_id": warehouse.company_id.id,
                        }
                    )
                updates["direct_sales_dispatch_location_id"] = dispatch.id

            operation_type = warehouse.direct_sales_operation_type_id
            if not operation_type:
                operation_type = PickingType.search(
                    [
                        ("warehouse_id", "=", warehouse.id),
                        ("code", "=", "internal"),
                        ("default_location_src_id", "=", warehouse.lot_stock_id.id),
                        ("default_location_dest_id", "=", dispatch.id),
                    ],
                    limit=1,
                )
                if not operation_type:
                    operation_type = PickingType.create(
                        {
                            "name": _("Direct Sales Preparation"),
                            "code": "internal",
                            "sequence_code": "DSP",
                            "warehouse_id": warehouse.id,
                            "company_id": warehouse.company_id.id,
                            "default_location_src_id": warehouse.lot_stock_id.id,
                            "default_location_dest_id": dispatch.id,
                            "show_operations": True,
                        }
                    )
                updates["direct_sales_operation_type_id"] = operation_type.id

            if updates:
                warehouse.with_context(skip_direct_sales_setup=True).write(updates)
        return True

    def action_initialize_direct_sales(self):
        self._ensure_direct_sales_setup()
        self.write({"direct_sales_enabled": True})
        return True

    def write(self, vals):
        result = super().write(vals)
        if (
            vals.get("direct_sales_enabled")
            and not self.env.context.get("skip_direct_sales_setup")
        ):
            self._ensure_direct_sales_setup()
        return result


class ResUsers(models.Model):
    _inherit = "res.users"

    direct_sales_warehouse_ids = fields.Many2many(
        "stock.warehouse",
        "stock_warehouse_direct_sales_user_rel",
        "user_id",
        "warehouse_id",
        string="Permitted Direct Sales Warehouses",
        domain="[('company_id', 'in', company_ids), ('direct_sales_enabled', '=', True)]",
    )
    direct_sales_approval_warehouse_ids = fields.Many2many(
        "stock.warehouse",
        "stock_warehouse_direct_sales_approver_rel",
        "user_id",
        "warehouse_id",
        string="Direct Sales Approval Warehouses",
        readonly=True,
    )
    direct_sales_channel_type = fields.Selection(
        [
            ("salesperson", "Salesperson (Pre-Order / Pickup)"),
            ("cash_van", "Cash Van Driver"),
        ],
        string="Direct Sales Channel Type",
        default="salesperson",
        required=True,
        help="Determines the isolated workflow & screens visible for this user.",
    )
    salesperson_cash_journal_id = fields.Many2one(
        "account.journal",
        string="Salesperson Custodian Cash Journal",
        domain="[('type', '=', 'cash'), ('company_id', 'in', company_ids)]",
        help="Custodian cash journal representing the salesperson's physical cash wallet.",
    )
    cash_wallet_balance = fields.Float(
        string="Cash Wallet Balance",
        compute="_compute_cash_wallet_balance",
        digits="Account",
        help="Total cash collected from clients that is currently held by this salesperson.",
    )

    def _compute_cash_wallet_balance(self):
        for user in self:
            if not user.salesperson_cash_journal_id:
                user.cash_wallet_balance = 0.0
                continue
            journal = user.salesperson_cash_journal_id
            account = journal.default_account_id
            if account:
                domain = [
                    ("account_id", "=", account.id),
                    ("parent_state", "=", "posted"),
                    ("company_id", "in", user.company_ids.ids),
                ]
                lines = self.env["account.move.line"].search(domain)
                user.cash_wallet_balance = sum(lines.mapped("balance"))
            else:
                user.cash_wallet_balance = 0.0
