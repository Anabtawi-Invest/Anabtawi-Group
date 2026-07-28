from odoo import Command
from odoo.tests import tagged

from .common import DirectSalesCommon


@tagged("post_install", "-at_install")
class TestDirectSalesWarehouseApproval(DirectSalesCommon):
    def test_only_enabled_permitted_warehouses_are_available(self):
        enabled = self.create_second_warehouse("EN2", enabled=True)
        disabled = self.create_second_warehouse("DS0", enabled=False)
        document = self.make_document()

        permitted = document._get_permitted_warehouses()

        self.assertIn(self.warehouse, permitted)
        self.assertIn(enabled, permitted)
        self.assertNotIn(disabled, permitted)

    def test_warehouse_stock_availability_is_location_scoped(self):
        second = self.create_second_warehouse("ST2")
        self.env["stock.quant"]._update_available_quantity(
            self.product, second.lot_stock_id, 35.0
        )
        document = self.make_document(quantity=120.0)

        self.assertEqual(document.line_ids.on_hand_quantity, 100.0)
        self.assertEqual(document.line_ids.free_quantity, 100.0)
        self.assertEqual(document.line_ids.shortage_quantity, 20.0)

    def test_full_approval_creates_one_selected_warehouse_picking(self):
        document = self.make_document(quantity=3.0)

        self.submit_and_approve(document)

        self.assertEqual(document.state, "warehouse_approved")
        self.assertEqual(len(document.picking_ids), 1)
        picking = document.picking_ids
        self.assertEqual(picking.location_id, self.warehouse.lot_stock_id)
        self.assertEqual(picking.direct_sales_warehouse_id, self.warehouse)
        self.assertEqual(picking.move_ids.product_uom_qty, 3.0)

    def test_partial_approval_creates_only_approved_quantity(self):
        document = self.make_document(quantity=7.0)
        document.action_submit_to_warehouse()
        wizard = self.env["direct.sales.partial.approval.wizard"].create(
            {
                "direct_invoice_id": document.id,
                "warehouse_comment": "Only four available for this request",
                "line_ids": [
                    Command.create(
                        {
                            "direct_invoice_line_id": document.line_ids.id,
                            "approved_quantity": 4.0,
                        }
                    )
                ],
            }
        )

        wizard.action_apply()

        self.assertEqual(document.state, "partially_approved")
        self.assertEqual(document.line_ids.approved_quantity, 4.0)
        self.assertEqual(document.picking_ids.move_ids.product_uom_qty, 4.0)

    def test_rejection_creates_no_stock_documents(self):
        document = self.make_document()
        document.action_submit_to_warehouse()

        document._reject_from_warehouse("Stock reserved for a prior commitment")

        self.assertEqual(document.state, "rejected")
        self.assertFalse(document.picking_ids)
        self.assertEqual(document.rejection_reason, "Stock reserved for a prior commitment")

    def test_picking_creation_is_idempotent(self):
        document = self.make_document()
        self.submit_and_approve(document)
        original_pickings = document.picking_ids

        document._ensure_approval_pickings()
        document._ensure_approval_pickings()

        self.assertEqual(document.picking_ids, original_pickings)
        self.assertEqual(len(document.picking_ids), 1)

    def test_multiwarehouse_allocations_create_separate_pickings_one_invoice(self):
        self.company.write(
            {
                "allow_multi_warehouse_fulfillment": True,
                "direct_sales_invoice_creation_policy": "on_warehouse_approval",
            }
        )
        second = self.create_second_warehouse("MW2")
        second.write(
            {
                "direct_sales_approval_user_ids": [Command.link(self.env.user.id)],
                "direct_sales_user_ids": [Command.link(self.env.user.id)],
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product, second.lot_stock_id, 10.0
        )
        document = self.make_document(
            quantity=6.0,
            line_values={
                "allocation_ids": [
                    Command.create(
                        {
                            "warehouse_id": self.warehouse.id,
                            "source_location_id": self.warehouse.lot_stock_id.id,
                            "requested_quantity": 2.0,
                        }
                    ),
                    Command.create(
                        {
                            "warehouse_id": second.id,
                            "source_location_id": second.lot_stock_id.id,
                            "requested_quantity": 4.0,
                        }
                    ),
                ]
            },
        )

        self.submit_and_approve(document)

        self.assertEqual(len(document.picking_ids), 2)
        self.assertEqual(
            set(document.picking_ids.mapped("direct_sales_warehouse_id")),
            {self.warehouse, second},
        )
        self.assertEqual(sum(document.picking_ids.move_ids.mapped("product_uom_qty")), 6.0)
        self.assertEqual(len(document.invoice_id), 1)
        self.assertEqual(document.invoice_id.invoice_line_ids.quantity, 6.0)
