from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import DirectSalesCommon


@tagged("post_install", "-at_install")
class TestDirectSalesSecurity(DirectSalesCommon):
    def create_role_user(self, login, group_xmlid, warehouses=()):
        user = self.env["res.users"].create(
            {
                "name": login.replace("_", " ").title(),
                "login": login,
                "company_id": self.company.id,
                "company_ids": [Command.set([self.company.id])],
                "group_ids": [Command.set([self.env.ref(group_xmlid).id])],
            }
        )
        if warehouses:
            user.direct_sales_warehouse_ids = [Command.set(list(warehouses.ids))]
        return user

    def test_salesperson_cannot_approve_warehouse_request(self):
        salesperson = self.create_role_user(
            "dsi_salesperson",
            "anabtawi_direct_sales_invoice.group_direct_invoice_user",
            self.warehouse,
        )
        document = self.make_document(user_id=salesperson.id)
        document.with_user(salesperson).action_submit_to_warehouse()

        with self.assertRaises(AccessError):
            document.with_user(salesperson)._approve_from_warehouse()

    def test_rpc_cannot_forge_workflow_or_approved_quantities(self):
        salesperson = self.create_role_user(
            "dsi_rpc_salesperson",
            "anabtawi_direct_sales_invoice.group_direct_invoice_user",
            self.warehouse,
        )
        document = self.make_document(user_id=salesperson.id)

        with self.assertRaises(AccessError):
            document.with_user(salesperson).write(
                {
                    "state": "warehouse_approved",
                    "warehouse_approved_by": salesperson.id,
                }
            )
        with self.assertRaises(AccessError):
            document.line_ids.with_user(salesperson).write(
                {"approved_quantity": document.line_ids.quantity}
            )

    def test_warehouse_user_cannot_change_selling_price(self):
        warehouse_user = self.create_role_user(
            "dsi_warehouse_user",
            "anabtawi_direct_sales_invoice.group_direct_invoice_warehouse_user",
            self.warehouse,
        )
        self.warehouse.direct_sales_user_ids = [Command.link(warehouse_user.id)]
        document = self.make_document()

        with self.assertRaises(AccessError):
            document.line_ids.with_user(warehouse_user).write(
                {
                    "price_unit": 70.0,
                    "price_override_reason": "Warehouse must not edit price",
                }
            )

    def test_sales_manager_can_approve_price_override(self):
        manager = self.create_role_user(
            "dsi_sales_manager",
            "anabtawi_direct_sales_invoice.group_direct_invoice_sales_manager",
            self.warehouse,
        )
        document = self.make_document(
            user_id=manager.id,
            line_values={
                "price_unit": 88.0,
                "price_override_reason": "Manager-approved customer exception",
            },
        )

        document.with_user(manager).action_approve_price_overrides()

        self.assertEqual(document.line_ids.price_override_state, "approved")
        self.assertEqual(document.line_ids.price_override_approved_by, manager)

    def test_accounting_user_can_open_register_payment(self):
        accounting_user = self.create_role_user(
            "dsi_accounting_user",
            "anabtawi_direct_sales_invoice.group_direct_invoice_accounting_user",
        )
        self.company.direct_sales_invoice_creation_policy = "on_warehouse_approval"
        document = self.make_document()
        self.submit_and_approve(document)
        document.invoice_id.action_post()

        action = document.with_user(accounting_user).action_register_payment()

        self.assertEqual(action["res_model"], "account.payment.register")
        self.assertEqual(action["context"]["active_ids"], document.invoice_id.ids)

    def test_warehouse_record_rule_hides_unauthorized_documents(self):
        second = self.create_second_warehouse("SEC")
        warehouse_user = self.create_role_user(
            "dsi_scoped_warehouse_user",
            "anabtawi_direct_sales_invoice.group_direct_invoice_warehouse_user",
            self.warehouse,
        )
        self.warehouse.direct_sales_user_ids = [Command.link(warehouse_user.id)]
        unauthorized_document = self.make_document(warehouse=second)

        visible = self.env["direct.sales.invoice"].with_user(warehouse_user).search(
            [("id", "=", unauthorized_document.id)]
        )

        self.assertFalse(visible)
