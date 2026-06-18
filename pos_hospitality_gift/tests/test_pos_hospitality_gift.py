from odoo.tests import tagged
from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("post_install", "-at_install")
class TestPosHospitalityGift(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gift_expense_account = cls.env["account.account"].search(
            [
                ("company_ids", "in", cls.company.id),
                ("account_type", "=", "expense"),
            ],
            limit=1,
        )
        cls.hospitality_payment_method = cls.env["pos.payment.method"].create(
            {
                "name": "Hospitality",
                "split_transactions": False,
                "type": "pay_later",
                "receivable_account_id": cls.company.account_default_pos_receivable_account_id.id,
                "company_id": cls.company.id,
            }
        )
        cls.company.write(
            {
                "gift_expense_account_id": cls.gift_expense_account.id,
            }
        )
        cls.hospitality_config = cls.env["pos.config"].create(
            {
                "name": "Hospitality Test POS",
                "journal_id": cls.company_data["default_journal_sale"].id,
                "invoice_journal_id": cls.company_data["default_journal_sale"].id,
                "payment_method_ids": [(6, 0, [cls.hospitality_payment_method.id])],
                "pricelist_id": cls.currency_pricelist.id,
                "available_pricelist_ids": [(6, 0, cls.currency_pricelist.ids)],
            }
        )
        cls.gift_product = cls.create_product(
            "Gift Product",
            cls.categ_basic,
            100.0,
            tax_ids=[cls.taxes["tax7"].id],
        )

    def _create_and_close_hospitality_session(self, line_payloads):
        self.config = self.hospitality_config
        session = self.open_new_session()
        order_data = self.create_ui_order_data(line_payloads, payments=[])
        self.env["pos.order"].sync_from_ui([order_data])
        session.close_session_from_ui()
        return session

    def test_gift_flag_is_stored_on_pos_order_line(self):
        self.config = self.hospitality_config
        self.open_new_session()
        order_data = self.create_ui_order_data(
            [
                {
                    "product": self.gift_product,
                    "quantity": 1,
                    "is_gift": True,
                    "gift_reason": "Hospitality",
                    "discount": 100,
                }
            ],
            payments=[],
        )
        synced = self.env["pos.order"].sync_from_ui([order_data])["pos.order"][0]
        order = self.env["pos.order"].browse(synced["id"])
        self.assertTrue(order.lines.is_gift)
        self.assertEqual(order.lines.gift_reason, "Hospitality")
        self.assertEqual(order.lines.discount, 100)

    def test_zero_hospitality_payment_is_added_for_gift_order(self):
        self.config = self.hospitality_config
        self.open_new_session()
        order_data = self.create_ui_order_data(
            [{"product": self.gift_product, "quantity": 1, "is_gift": True, "discount": 100}],
            payments=[],
        )
        synced = self.env["pos.order"].sync_from_ui([order_data])["pos.order"][0]
        order = self.env["pos.order"].browse(synced["id"])
        hospitality_payments = order.payment_ids.filtered(
            lambda payment: payment.payment_method_id == self.hospitality_payment_method
            and not payment.is_change
        )
        self.assertEqual(len(hospitality_payments), 1)
        self.assertEqual(hospitality_payments.amount, 0.0)
