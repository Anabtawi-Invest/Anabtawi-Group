from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import DirectSalesCommon


@tagged("post_install", "-at_install")
class TestDirectSalesStockFlow(DirectSalesCommon):
    def test_direct_delivery_uses_selected_warehouse_to_customer(self):
        document = self.make_document(quantity=4.0)

        self.submit_and_approve(document)

        picking = document.picking_ids
        self.assertEqual(picking.direct_sales_stage, "release")
        self.assertEqual(picking.location_id, self.warehouse.lot_stock_id)
        self.assertEqual(
            picking.location_dest_id, self.partner.property_stock_customer
        )
        self.assertEqual(picking.move_ids.direct_invoice_line_id, document.line_ids)

    def test_two_step_dispatch_then_customer(self):
        self.warehouse.direct_sales_stock_flow = "dispatch_then_customer"
        document = self.make_document(quantity=3.0)
        self.submit_and_approve(document)
        preparation = document.picking_ids.filtered(
            lambda picking: picking.direct_sales_stage == "preparation"
        )

        self.assertEqual(preparation.location_id, self.warehouse.lot_stock_id)
        self.assertEqual(
            preparation.location_dest_id,
            self.warehouse.direct_sales_dispatch_location_id,
        )
        self.validate_picking(preparation)
        document.action_prepare_goods()
        release = document.picking_ids.filtered(
            lambda picking: picking.direct_sales_stage == "release"
        )

        self.assertEqual(
            release.location_id, self.warehouse.direct_sales_dispatch_location_id
        )
        self.assertEqual(
            release.location_dest_id, self.partner.property_stock_customer
        )
        self.assertEqual(release.move_ids.product_uom_qty, 3.0)

    def test_released_quantity_cannot_exceed_approved(self):
        document = self.make_document(quantity=2.0)
        self.submit_and_approve(document)

        with self.assertRaisesRegex(
            ValidationError, "Released quantity cannot exceed approved quantity"
        ):
            document.line_ids.with_context(
                direct_sales_warehouse_write=True
            ).released_quantity = 3.0

    def test_standard_backorder_preserves_direct_sales_links(self):
        document = self.make_document(quantity=2.0)
        self.submit_and_approve(document)
        picking = document.picking_ids

        backorder = picking._create_backorder_picking()

        self.assertEqual(backorder.backorder_id, picking)
        self.assertEqual(backorder.direct_invoice_id, document)
        self.assertEqual(backorder.direct_sales_warehouse_id, self.warehouse)
        self.assertEqual(backorder.direct_sales_stage, "release")

    def test_released_lot_is_linked_to_direct_line(self):
        product, lot = self.create_lot_product()
        document = self.make_document(quantity=2.0, product=product)
        self.submit_and_approve(document)
        document.action_prepare_goods()
        release = document.picking_ids.filtered(
            lambda picking: picking.direct_sales_stage == "release"
        )
        self.mark_picking_quantities_done(release)
        release.move_line_ids.write({"lot_id": lot.id})

        document._confirm_goods_release("Lot Customer")

        self.assertIn(lot, document.line_ids.lot_ids)
        self.assertEqual(document.line_ids.released_quantity, 2.0)

    def test_return_flow_uses_standard_wizard_and_preserves_links(self):
        document = self.make_document()
        self.submit_and_approve(document)
        document.action_prepare_goods()
        release = document.picking_ids.filtered(
            lambda picking: picking.direct_sales_stage == "release"
        )
        self.mark_picking_quantities_done(release)
        document._confirm_goods_release("Return Test Customer")

        action = document.action_create_return()
        wizard = (
            self.env["stock.return.picking"]
            .with_context(**action["context"])
            .create({"picking_id": release.id})
        )
        wizard.product_return_moves.quantity = 1.0
        return_action = wizard.action_create_returns()
        return_picking = self.env["stock.picking"].browse(
            return_action["res_id"]
        )

        self.assertEqual(action["res_model"], "stock.return.picking")
        self.assertEqual(action["context"]["active_id"], release.id)
        self.assertEqual(return_picking.return_id, release)
        self.assertEqual(return_picking.direct_invoice_id, document)
        self.assertEqual(return_picking.direct_sales_stage, "return")
        self.assertEqual(
            return_picking.move_ids.direct_invoice_line_id, document.line_ids
        )
