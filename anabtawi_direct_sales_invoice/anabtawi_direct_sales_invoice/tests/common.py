from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class DirectSalesCommon(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write(
            {
                "direct_sales_enabled": True,
                "direct_sales_invoice_creation_policy": "on_goods_release",
                "direct_sales_auto_post_invoice": False,
                "direct_sales_stock_flow": "direct_delivery",
                "cash_customer_release_policy": "allow_before_payment",
                "allow_partial_warehouse_approval": True,
                "allow_multi_warehouse_fulfillment": False,
                "direct_sales_price_override_approval": True,
            }
        )
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.warehouse.write(
            {
                "direct_sales_stock_flow": "direct_delivery",
                "direct_sales_enabled": True,
            }
        )
        cls.warehouse.write(
            {
                "direct_sales_approval_user_ids": [Command.link(cls.env.user.id)],
                "direct_sales_user_ids": [Command.link(cls.env.user.id)],
            }
        )

        cls.product = cls.product_a
        cls.product.write(
            {
                "name": "Direct Sales Test Product",
                "is_storable": True,
                "tracking": "none",
                "lst_price": 100.0,
                "standard_price": 40.0,
            }
        )
        cls.pricelist = cls.env["product.pricelist"].create(
            {
                "name": "DSI Test Pricelist - Never Print",
                "currency_id": cls.company.currency_id.id,
                "company_id": cls.company.id,
            }
        )
        cls.partner = cls.partner_a
        cls.partner.with_company(cls.company).write(
            {
                "property_product_pricelist": cls.pricelist.id,
                "property_payment_term_id": cls.pay_terms_a.id,
            }
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.warehouse.lot_stock_id, 100.0
        )

    def make_document(
        self,
        quantity=2.0,
        product=None,
        partner=None,
        warehouse=None,
        line_values=None,
        **document_values,
    ):
        product = product or self.product
        partner = partner or self.partner
        warehouse = warehouse or self.warehouse
        values = {
            "partner_id": partner.id,
            "warehouse_id": warehouse.id,
            "user_id": self.env.user.id,
            "line_ids": [
                Command.create(
                    {
                        "product_id": product.id,
                        "product_uom_id": product.uom_id.id,
                        "quantity": quantity,
                        "tax_ids": [Command.set(product.taxes_id.ids)],
                        **(line_values or {}),
                    }
                )
            ],
        }
        values.update(document_values)
        return self.env["direct.sales.invoice"].create(values)

    def submit_and_approve(self, document, partial_quantity=None):
        document.action_submit_to_warehouse()
        if partial_quantity is not None:
            document.line_ids.with_context(
                direct_sales_warehouse_write=True
            ).write(
                {
                    "approved_quantity": partial_quantity,
                    "warehouse_status": "partial",
                }
            )
            document._approve_from_warehouse(partial=True, comment="Test partial")
        else:
            document._approve_from_warehouse(comment="Test approval")
        return document.picking_ids

    def mark_picking_quantities_done(self, picking):
        picking.action_assign()
        for move in picking.move_ids:
            remaining = move.product_uom_qty
            for move_line in move.move_line_ids:
                quantity = min(remaining, move_line.quantity or remaining)
                move_line.write({"quantity": quantity, "picked": True})
                remaining -= quantity
            if remaining:
                self.env["stock.move.line"].create(
                    {
                        "move_id": move.id,
                        "picking_id": picking.id,
                        "product_id": move.product_id.id,
                        "product_uom_id": move.product_uom.id,
                        "location_id": move.location_id.id,
                        "location_dest_id": move.location_dest_id.id,
                        "quantity": remaining,
                        "picked": True,
                    }
                )

    def validate_picking(self, picking):
        self.mark_picking_quantities_done(picking)
        result = picking.button_validate()
        self.assertFalse(
            isinstance(result, dict),
            "A full-quantity test transfer must not open an immediate/backorder wizard.",
        )
        self.assertEqual(picking.state, "done")
        return picking

    def create_second_warehouse(self, code="DS2", enabled=True):
        warehouse = self.env["stock.warehouse"].create(
            {
                "name": f"Direct Sales Warehouse {code}",
                "code": code,
                "company_id": self.company.id,
            }
        )
        warehouse.write(
            {
                "direct_sales_stock_flow": "direct_delivery",
                "direct_sales_enabled": enabled,
            }
        )
        return warehouse

    def create_lot_product(self):
        product = self._create_product(
            name="Direct Sales Lot Product",
            lst_price=75.0,
            standard_price=25.0,
            uom_id=self.uom_unit.id,
            is_storable=True,
            tracking="lot",
        )
        lot = self.env["stock.lot"].create(
            {
                "name": "DSI-LOT-001",
                "product_id": product.id,
                "company_id": self.company.id,
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            product,
            self.warehouse.lot_stock_id,
            10.0,
            lot_id=lot,
        )
        return product, lot

    @staticmethod
    def today():
        return fields.Date.today()
