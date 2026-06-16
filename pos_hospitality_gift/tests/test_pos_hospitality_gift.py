from odoo.tests import tagged
from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("post_install", "-at_install")
class TestPosHospitalityGift(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hospitality_clearing_account = cls.copy_account(
            cls.company.account_default_pos_receivable_account_id,
            {"name": "Hospitality Clearing"},
        )
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
                "receivable_account_id": cls.hospitality_clearing_account.id,
                "company_id": cls.company.id,
            }
        )
        cls.company.write(
            {
                "hospitality_payment_method_id": cls.hospitality_payment_method.id,
                "hospitality_clearing_account_id": cls.hospitality_clearing_account.id,
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
        order_data = self.create_ui_order_data(
            line_payloads,
            payments=[(self.hospitality_payment_method, 107.0 * len(line_payloads))],
        )
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
                }
            ],
            payments=[(self.hospitality_payment_method, 107.0)],
        )
        synced = self.env["pos.order"].sync_from_ui([order_data])["pos.order"][0]
        order = self.env["pos.order"].browse(synced["id"])
        self.assertTrue(order.lines.is_gift)
        self.assertEqual(order.lines.gift_reason, "Hospitality")

    def test_session_closing_creates_hospitality_settlement(self):
        session = self._create_and_close_hospitality_session(
            [{"product": self.gift_product, "quantity": 1, "is_gift": True}]
        )
        settlement_move = session.hospitality_settlement_move_id
        self.assertTrue(settlement_move, "Settlement move should be created on session close.")
        self.assertEqual(settlement_move.state, "posted")
        self.assertEqual(len(settlement_move.line_ids), 2)
        self.assertAlmostEqual(
            sum(settlement_move.line_ids.filtered(lambda l: l.account_id == self.gift_expense_account).mapped("debit")),
            107.0,
            places=2,
        )
        self.assertAlmostEqual(
            sum(
                settlement_move.line_ids.filtered(
                    lambda l: l.account_id == self.hospitality_clearing_account
                ).mapped("credit")
            ),
            107.0,
            places=2,
        )

    def test_settlement_generation_is_idempotent(self):
        self.config = self.hospitality_config
        session = self.open_new_session()
        order_data_1 = self.create_ui_order_data(
            [{"product": self.gift_product, "quantity": 1, "is_gift": True}],
            payments=[(self.hospitality_payment_method, 107.0)],
        )
        order_data_2 = self.create_ui_order_data(
            [{"product": self.gift_product, "quantity": 1, "is_gift": True}],
            payments=[(self.hospitality_payment_method, 107.0)],
        )
        self.env["pos.order"].sync_from_ui([order_data_1, order_data_2])
        session.close_session_from_ui()
        first_move = session.hospitality_settlement_move_id
        self.assertTrue(first_move)
        session._create_hospitality_settlement_move()
        self.assertEqual(session.hospitality_settlement_move_id, first_move)
