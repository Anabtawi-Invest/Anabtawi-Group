# -*- coding: utf-8 -*-
import base64
import io
from collections import defaultdict
from datetime import datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class BranchSupplyFlowWizard(models.TransientModel):
    _name = "branch.supply.flow.wizard"
    _description = "Branch Supply Flow Report Wizard"

    date_from = fields.Datetime(
        string="From (Effective Date)",
        required=True,
        default=lambda self: datetime.combine(
            fields.Date.context_today(self).replace(day=1), time.min
        ),
    )
    date_to = fields.Datetime(
        string="To (Effective Date)",
        required=True,
        default=lambda self: datetime.combine(fields.Date.context_today(self), time.max),
    )
    all_branch_locations = fields.Boolean(
        string="All Branch Locations",
        default=True,
        help="Include every branch stock location (warehouse stock location).",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Branch Location",
        domain="[('usage', '=', 'internal')]",
        help="Branch stock location used to filter receipt transfers.",
    )
    all_dispatch_operation_types = fields.Boolean(
        string="All Dispatch Operation Types",
        default=True,
        help="Include all internal operation types for factory-to-transit transfers.",
    )
    dispatch_picking_type_ids = fields.Many2many(
        "stock.picking.type",
        "branch_supply_flow_wiz_dispatch_pt_rel",
        "wizard_id",
        "picking_type_id",
        string="Dispatch Operation Types",
        domain="[('code', '=', 'internal')]",
        help="Factory to intermediate / transit transfers (sent quantities).",
    )
    all_receipt_operation_types = fields.Boolean(
        string="All Receipt Operation Types",
        default=True,
        help="Include all internal operation types for transit-to-branch transfers.",
    )
    receipt_picking_type_ids = fields.Many2many(
        "stock.picking.type",
        "branch_supply_flow_wiz_receipt_pt_rel",
        "wizard_id",
        "picking_type_id",
        string="Receipt Operation Types",
        domain="[('code', '=', 'internal')]",
        help="Intermediate to branch stock transfers (received quantities).",
    )
    all_pos_configs = fields.Boolean(
        string="All POS Branches",
        default=True,
        help="Include all POS configs for the selected branch(es).",
    )
    pos_config_ids = fields.Many2many(
        "pos.config",
        string="POS Branches",
        help="Leave empty to include all POS configs linked to the branch warehouse.",
    )
    line_ids = fields.One2many(
        "branch.supply.flow.report.line",
        "wizard_id",
        string="Report Lines",
        readonly=True,
    )

    @api.onchange("all_branch_locations")
    def _onchange_all_branch_locations(self):
        if self.all_branch_locations:
            self.location_id = False

    @api.onchange("all_dispatch_operation_types")
    def _onchange_all_dispatch_operation_types(self):
        if self.all_dispatch_operation_types:
            self.dispatch_picking_type_ids = [(5, 0, 0)]

    @api.onchange("all_receipt_operation_types")
    def _onchange_all_receipt_operation_types(self):
        if self.all_receipt_operation_types:
            self.receipt_picking_type_ids = [(5, 0, 0)]

    @api.onchange("all_pos_configs")
    def _onchange_all_pos_configs(self):
        if self.all_pos_configs:
            self.pos_config_ids = [(5, 0, 0)]

    @api.onchange("location_id")
    def _onchange_location_id(self):
        if not self.location_id or self.all_pos_configs:
            return
        configs = self._get_pos_configs_for_location(self.location_id)
        self.pos_config_ids = configs

    def _get_internal_picking_types(self):
        return self.env["stock.picking.type"].search([
            ("code", "=", "internal"),
            ("company_id", "in", self.env.companies.ids),
        ])

    def _get_branch_stock_locations(self):
        self.ensure_one()
        if self.all_branch_locations:
            warehouses = self.env["stock.warehouse"].search([
                ("company_id", "in", self.env.companies.ids),
            ])
            return warehouses.mapped("lot_stock_id")
        if not self.location_id:
            raise UserError(_("Please select a branch location or enable All Branch Locations."))
        return self.location_id

    def _get_location_ids(self, location):
        return self.env["stock.location"].search([("id", "child_of", location.id)]).ids

    def _get_branch_stock_location_ids(self, branch_locations=None):
        branch_locations = branch_locations or self._get_branch_stock_locations()
        if not branch_locations:
            return []
        location_ids = set()
        for location in branch_locations:
            location_ids.update(self._get_location_ids(location))
        return list(location_ids)

    def _get_branch_warehouse(self, branch_location):
        warehouse = branch_location.warehouse_id
        if not warehouse:
            warehouse = self.env["stock.warehouse"].search(
                [("lot_stock_id", "parent_of", branch_location.id)],
                limit=1,
            )
        return warehouse

    def _get_dispatch_picking_types(self):
        self.ensure_one()
        if self.all_dispatch_operation_types:
            return self._get_internal_picking_types()
        if not self.dispatch_picking_type_ids:
            raise UserError(_("Please select dispatch operation types or enable All Dispatch Operation Types."))
        return self.dispatch_picking_type_ids

    def _get_receipt_picking_types(self):
        self.ensure_one()
        if self.all_receipt_operation_types:
            return self._get_internal_picking_types()
        if not self.receipt_picking_type_ids:
            raise UserError(_("Please select receipt operation types or enable All Receipt Operation Types."))
        return self.receipt_picking_type_ids

    def _get_pos_configs_for_location(self, location):
        warehouse = location.warehouse_id
        if not warehouse:
            warehouse = self.env["stock.warehouse"].search(
                [("lot_stock_id", "parent_of", location.id)],
                limit=1,
            )
        if warehouse:
            return self.env["pos.config"].search([("warehouse_id", "=", warehouse.id)])
        return self.env["pos.config"]

    def _move_done_qty_product_uom(self, move):
        return move.product_uom._compute_quantity(
            move.quantity, move.product_id.uom_id, round=False
        )

    def _move_demand_qty_product_uom(self, move):
        return move.product_uom._compute_quantity(
            move.product_uom_qty, move.product_id.uom_id, round=False
        )

    def _picking_return_qty_by_product(self, picking):
        qty_by_product = defaultdict(float)
        for return_picking in picking.return_ids.filtered(lambda p: p.state == "done"):
            for move in return_picking.move_ids.filtered(lambda m: m.state == "done"):
                qty_by_product[move.product_id.id] += self._move_done_qty_product_uom(move)
        return qty_by_product

    def _base_picking_domain(self, date_from, date_to):
        return [
            ("state", "=", "done"),
            ("return_id", "=", False),
            ("date_done", ">=", date_from),
            ("date_done", "<=", date_to),
        ]

    def _get_dispatch_pickings(self, date_from, date_to, branch_location):
        """Dispatch transfers: factory -> intermediate/transit for this branch."""
        self.ensure_one()
        picking_types = self._get_dispatch_picking_types()
        branch_stock_ids = self._get_location_ids(branch_location)
        receipt_pickings = self._get_receipt_pickings(date_from, date_to, branch_location)

        pickings = self.env["stock.picking"]

        # Primary: dispatch transfers linked to branch receipts via Source Document (origin).
        origin_names = list({name for name in receipt_pickings.mapped("origin") if name})
        if origin_names:
            pickings |= self.env["stock.picking"].search([
                *self._base_picking_domain(date_from, date_to),
                ("name", "in", origin_names),
                ("picking_type_id", "in", picking_types.ids),
            ])

        # Secondary: direct dispatch to intermediate locations (not branch stock).
        direct_domain = [
            *self._base_picking_domain(date_from, date_to),
            ("picking_type_id", "in", picking_types.ids),
            ("location_dest_id", "not in", branch_stock_ids),
        ]
        warehouse = self._get_branch_warehouse(branch_location)
        if warehouse:
            direct_domain.append(("location_dest_id.warehouse_id", "=", warehouse.id))
        pickings |= self.env["stock.picking"].search(direct_domain)
        return pickings

    def _get_receipt_pickings(self, date_from, date_to, branch_location):
        self.ensure_one()
        picking_types = self._get_receipt_picking_types()
        location_ids = self._get_location_ids(branch_location)
        domain = self._base_picking_domain(date_from, date_to)
        domain.extend([
            ("picking_type_id", "in", picking_types.ids),
            ("location_dest_id", "in", location_ids),
        ])
        return self.env["stock.picking"].search(domain)

    def _aggregate_transfer_quantities(self, pickings, include_requested=False):
        aggregated = defaultdict(lambda: {
            "requested": 0.0,
            "done": 0.0,
            "returns": 0.0,
        })
        for picking in pickings:
            return_qty = self._picking_return_qty_by_product(picking)
            for move in picking.move_ids.filtered(lambda m: m.state == "done"):
                product_id = move.product_id.id
                if include_requested:
                    aggregated[product_id]["requested"] += self._move_demand_qty_product_uom(move)
                aggregated[product_id]["done"] += self._move_done_qty_product_uom(move)
            for product_id, qty in return_qty.items():
                aggregated[product_id]["returns"] += qty
        return aggregated

    def _get_pos_config_ids_for_branch(self, branch_location):
        self.ensure_one()
        if self.all_pos_configs or not self.pos_config_ids:
            return self._get_pos_configs_for_location(branch_location).ids
        return self.pos_config_ids.ids

    def _get_pos_sold_qty_by_product(self, product_ids, date_from, date_to, branch_location):
        if not product_ids:
            return {}
        domain = [
            ("order_id.state", "in", ("paid", "done")),
            ("order_id.date_order", ">=", date_from),
            ("order_id.date_order", "<=", date_to),
            ("product_id", "in", list(product_ids)),
        ]
        config_ids = self._get_pos_config_ids_for_branch(branch_location)
        if config_ids:
            domain.append(("order_id.config_id", "in", config_ids))

        sold_by_product = defaultdict(float)
        lines = self.env["pos.order.line"].search(domain)
        for line in lines:
            refunded = line.refunded_qty or 0.0
            if line.qty >= 0:
                sold_by_product[line.product_id.id] += max(line.qty - refunded, 0.0)
            else:
                sold_by_product[line.product_id.id] += line.qty
        return sold_by_product

    def _build_branch_report_values(self, branch_location, date_from, date_to):
        dispatch_data = self._aggregate_transfer_quantities(
            self._get_dispatch_pickings(date_from, date_to, branch_location),
            include_requested=True,
        )
        receipt_data = self._aggregate_transfer_quantities(
            self._get_receipt_pickings(date_from, date_to, branch_location),
            include_requested=False,
        )

        product_ids = set(dispatch_data.keys()) | set(receipt_data.keys())
        sold_data = self._get_pos_sold_qty_by_product(
            product_ids, date_from, date_to, branch_location
        )
        product_ids |= set(sold_data.keys())

        vals_list = []
        Product = self.env["product.product"]
        for product_id in sorted(product_ids):
            product = Product.browse(product_id)
            dispatch = dispatch_data.get(product_id, {})
            receipt = receipt_data.get(product_id, {})
            sent_net = dispatch.get("done", 0.0) - dispatch.get("returns", 0.0)
            received_net = receipt.get("done", 0.0) - receipt.get("returns", 0.0)
            sold_qty = sold_data.get(product_id, 0.0)
            vals_list.append({
                "location_id": branch_location.id,
                "location_name": branch_location.complete_name,
                "product_id": product_id,
                "uom_id": product.uom_id.id,
                "uom_name": product.uom_id.display_name,
                "requested_qty": dispatch.get("requested", 0.0),
                "sent_qty": sent_net,
                "sent_return_qty": dispatch.get("returns", 0.0),
                "received_qty": received_net,
                "received_return_qty": receipt.get("returns", 0.0),
                "sold_qty": sold_qty,
                "variance_sent_received": sent_net - received_net,
                "variance_received_sold": received_net - sold_qty,
            })
        return vals_list

    def _build_report_values(self):
        self.ensure_one()
        date_from = fields.Datetime.to_string(self.date_from)
        date_to = fields.Datetime.to_string(self.date_to)
        branch_locations = self._get_branch_stock_locations()
        if not branch_locations:
            raise UserError(_("No branch stock locations were found."))

        vals_list = []
        for branch_location in branch_locations:
            vals_list.extend(
                self._build_branch_report_values(branch_location, date_from, date_to)
            )
        return vals_list

    def action_generate_report(self):
        self.ensure_one()
        self.line_ids.unlink()
        vals_list = self._build_report_values()
        if not vals_list:
            raise UserError(_("No data found for the selected filters."))
        self.write({"line_ids": [(0, 0, vals) for vals in vals_list]})
        return {
            "name": _("Branch Supply Flow Report"),
            "type": "ir.actions.act_window",
            "res_model": "branch.supply.flow.report.line",
            "view_mode": "list,pivot",
            "domain": [("wizard_id", "=", self.id)],
            "context": {"search_default_group_by_location": 1},
        }

    def _generate_xlsx_content(self):
        self.ensure_one()
        import xlsxwriter  # pylint: disable=import-outside-toplevel

        if not self.line_ids:
            vals_list = self._build_report_values()
            if not vals_list:
                raise UserError(_("No data found for the selected filters."))
            self.write({"line_ids": [(0, 0, vals) for vals in vals_list]})

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet(_("Branch Supply Flow"))
        sheet.right_to_left()

        header_style = workbook.add_format({
            "bold": True,
            "bg_color": "#D9E1F2",
            "border": 1,
            "align": "center",
        })
        text_style = workbook.add_format({"border": 1})
        number_style = workbook.add_format({"border": 1, "num_format": "#,##0.00"})

        headers = [
            _("Branch Location"),
            _("Product"),
            _("Unit of Measure"),
            _("Requested Qty"),
            _("Sent Qty (Net)"),
            _("Sent Returns"),
            _("Received Qty (Net)"),
            _("Received Returns"),
            _("Sold Qty (POS)"),
            _("Sent - Received"),
            _("Received - Sold"),
        ]
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_style)

        sheet.set_column(0, 0, 30)
        sheet.set_column(1, 1, 45)
        sheet.set_column(2, 2, 16)
        sheet.set_column(3, 10, 18)

        row = 1
        for line in self.line_ids.sorted(
            key=lambda rec: (rec.location_id.display_name, rec.product_id.display_name)
        ):
            sheet.write(row, 0, line.location_name or line.location_id.display_name, text_style)
            sheet.write(row, 1, line.product_id.display_name, text_style)
            sheet.write(row, 2, line.uom_name or (line.uom_id.display_name or ""), text_style)
            sheet.write_number(row, 3, line.requested_qty, number_style)
            sheet.write_number(row, 4, line.sent_qty, number_style)
            sheet.write_number(row, 5, line.sent_return_qty, number_style)
            sheet.write_number(row, 6, line.received_qty, number_style)
            sheet.write_number(row, 7, line.received_return_qty, number_style)
            sheet.write_number(row, 8, line.sold_qty, number_style)
            sheet.write_number(row, 9, line.variance_sent_received, number_style)
            sheet.write_number(row, 10, line.variance_received_sold, number_style)
            row += 1

        workbook.close()
        return output.getvalue()

    def action_export_excel(self):
        self.ensure_one()
        content = self._generate_xlsx_content()
        filename = "branch_supply_flow_report.xlsx"
        attachment = self.env["ir.attachment"].create({
            "name": filename,
            "type": "binary",
            "datas": base64.b64encode(content),
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }
