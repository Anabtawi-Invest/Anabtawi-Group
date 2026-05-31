import odoo

from odoo.addons.point_of_sale.tests.common import TestPoSCommon
from odoo.exceptions import UserError, ValidationError


@odoo.tests.tagged("post_install", "-at_install")
class TestPosDeliveryAmount(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.delivery_journal = cls.env["account.journal"].create(
            {
                "name": "POS Delivery Journal",
                "code": "PDLJ",
                "type": "general",
                "company_id": cls.company.id,
            }
        )
        cls.delivery_intermediate_account = cls.copy_account(
            cls.company_data["default_journal_cash"].default_account_id,
            {
                "name": "POS Delivery Intermediate",
                "code": "PDL100",
            },
        )

    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        self.config.write(
            {
                "delivery_journal_id": self.delivery_journal.id,
                "delivery_intermediate_account_id": self.delivery_intermediate_account.id,
            }
        )

    def test_action_process_delivery_amount_creates_posted_move(self):
        session = self.open_new_session(opening_cash=250.0)
        session.post_closing_cash_details(220.0)
        session.update_closing_control_state_session("Session closing with delivery amount")

        result = session.action_process_delivery_amount(150.0)
        self.assertTrue(result["successful"])
        self.assertEqual(session.delivery_amount, 150.0)
        self.assertTrue(session.delivery_move_id)
        self.assertEqual(session.delivery_move_id.state, "posted")
        self.assertEqual(session.delivery_move_id.journal_id, self.delivery_journal)

        debit_line = session.delivery_move_id.line_ids.filtered(
            lambda line: line.account_id == self.delivery_intermediate_account
        )
        credit_line = session.delivery_move_id.line_ids.filtered(
            lambda line: line.account_id == session.cash_journal_id.default_account_id
        )
        self.assertTrue(debit_line)
        self.assertTrue(credit_line)
        self.assertEqual(debit_line.debit, 150.0)
        self.assertEqual(credit_line.credit, 150.0)

    def test_action_process_delivery_amount_rejects_excess_amount(self):
        session = self.open_new_session(opening_cash=200.0)
        session.post_closing_cash_details(100.0)
        session.update_closing_control_state_session("Closing")

        with self.assertRaisesRegex(
            ValidationError, "Delivery Amount cannot exceed counted cash balance."
        ):
            session.action_process_delivery_amount(120.0)

    def test_action_process_delivery_amount_zero_does_not_create_move(self):
        session = self.open_new_session(opening_cash=100.0)
        session.post_closing_cash_details(80.0)
        session.update_closing_control_state_session("Closing")

        result = session.action_process_delivery_amount(0.0)
        self.assertTrue(result["successful"])
        self.assertEqual(session.delivery_amount, 0.0)
        self.assertFalse(session.delivery_move_id)

    def test_action_process_delivery_amount_requires_configuration(self):
        session = self.open_new_session(opening_cash=50.0)
        session.post_closing_cash_details(50.0)
        session.update_closing_control_state_session("Closing")
        session.config_id.delivery_journal_id = False

        with self.assertRaises(UserError):
            session.action_process_delivery_amount(10.0)
