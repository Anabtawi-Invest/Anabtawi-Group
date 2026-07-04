import logging

from odoo.tests import new_test_user, tagged
from odoo.exceptions import AccessError, UserError

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.account_check_print.models.account_payment import (
    _check_print_font_base64,
    get_check_print_font_diagnostics,
)

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestAccountCheckPrint(AccountTestInvoicingCommon):
    """Exercise numbering, lifecycle, security, and QWeb integration."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.layout = cls.env["account.check.layout"].create({
            "name": "Test Business Check",
            "company_id": cls.env.company.id,
        })
        cls.journal = cls.company_data["default_journal_bank"]
        cls.journal.write({
            "enable_check_printing": True,
            "check_layout_id": cls.layout.id,
            "next_check_number": 1001,
            "print_language": "en",
            "stock_type": "preprinted",
        })
        cls.accounting_user = new_test_user(
            cls.env,
            login="check_accounting_user",
            groups="account.group_account_user",
            company_id=cls.env.company.id,
        )
        cls._log_font_diagnostics("setUpClass")

    @classmethod
    def _log_font_diagnostics(cls, label):
        diagnostics = get_check_print_font_diagnostics()
        _logger.info("account_check_print test [%s] font diagnostics: %s", label, diagnostics)

    def _log_html_diagnostics(self, label, html, expected=None):
        html_bytes = html if isinstance(html, bytes) else html.encode("utf-8")
        markers = {
            "Check Print DejaVu": b"Check Print DejaVu" in html_bytes,
            "data:application/font-ttf": b"data:application/font-ttf" in html_bytes,
            "DejaVuSans.ttf": b"DejaVuSans.ttf" in html_bytes,
            "o_check_print_page": b"o_check_print_page" in html_bytes,
        }
        if expected:
            markers[f"expected:{expected!r}"] = expected.encode("utf-8") in html_bytes
        _logger.info(
            "account_check_print test [%s] HTML diagnostics: html_len=%s markers=%s snippet=%r",
            label,
            len(html_bytes),
            markers,
            html_bytes[:800],
        )

    def _create_posted_payment(self, amount=125.0):
        """Create one posted outbound vendor payment using the test bank."""
        payment = self.init_payment(-amount, post=False, partner=self.partner_a)
        payment.journal_id = self.journal
        payment.payment_method_line_id = self.outbound_payment_method_line
        payment.action_post()
        return payment

    def test_numbering_and_duplicate_print_protection(self):
        self._log_font_diagnostics("test_numbering_and_duplicate_print_protection")
        payment = self._create_posted_payment()
        payment.action_print_check()
        self.assertEqual(payment.check_number, "1001")
        self.assertEqual(self.journal.next_check_number, 1002)
        self.assertTrue(payment.printed)
        self.assertEqual(payment.check_history_ids.event_type, "print")
        with self.assertRaises(UserError):
            payment.action_print_check()

    def test_preview_does_not_consume_number(self):
        self._log_font_diagnostics("test_preview_does_not_consume_number")
        payment = self._create_posted_payment()
        before = self.journal.next_check_number
        action = payment.with_user(self.accounting_user).action_preview_check()
        self.assertEqual(action["type"], "ir.actions.report")
        self.assertFalse(payment.check_number)
        self.assertEqual(self.journal.next_check_number, before)

    def test_reprint_and_void_are_audited(self):
        self._log_font_diagnostics("test_reprint_and_void_are_audited")
        payment = self._create_posted_payment()
        payment.action_print_check()
        payment._reprint_check("Printer jam damaged the first copy")
        self.assertEqual(payment.reprinted_count, 1)
        payment._void_check("Vendor bank details changed")
        self.assertTrue(payment.voided)
        self.assertEqual(payment.check_history_count, 3)
        self.assertEqual(
            set(payment.check_history_ids.mapped("event_type")),
            {"print", "reprint", "void"},
        )
        with self.assertRaises(UserError):
            payment._reprint_check("Should fail")

    def test_accounting_user_cannot_print_or_void(self):
        self._log_font_diagnostics("test_accounting_user_cannot_print_or_void")
        payment = self._create_posted_payment()
        with self.assertRaises(AccessError):
            payment.with_user(self.accounting_user).action_print_check()

    def test_bundled_font_is_available(self):
        diagnostics = get_check_print_font_diagnostics()
        _logger.info("account_check_print test [test_bundled_font_is_available]: %s", diagnostics)
        self.assertTrue(
            _check_print_font_base64(),
            f"DejaVuSans.ttf must be present in account_check_print/static/src/fonts/. "
            f"Diagnostics: {diagnostics}",
        )

    def test_report_html_and_dynamic_paperformat(self):
        self._log_font_diagnostics("test_report_html_and_dynamic_paperformat")
        payment = self._create_posted_payment()
        payment.action_print_check()
        report = self.env.ref("account_check_print.action_report_check")
        selected = report.with_context(
            active_id=payment.id, active_ids=payment.ids
        ).get_paperformat()
        self.assertEqual(selected, self.layout.paperformat_id)
        html, _report_type = report._render_qweb_html(
            report.report_name, payment.ids, data={}
        )
        self._log_html_diagnostics(
            "test_report_html_and_dynamic_paperformat",
            html,
            expected=self.partner_a.name,
        )
        self.assertIn(
            self.partner_a.name.encode(),
            html,
            f"Partner name missing from report HTML. diagnostics={get_check_print_font_diagnostics()}",
        )
        self.assertIn(b"1001", html, "Check number missing from report HTML.")
        self.assertIn(
            b"Check Print DejaVu",
            html,
            f"Check font marker missing from report HTML. diagnostics={get_check_print_font_diagnostics()}",
        )

    def test_arabic_text_renders_in_check_report(self):
        self._log_font_diagnostics("test_arabic_text_renders_in_check_report")
        arabic_name = "الشركة العالمية"
        partner = self.env["res.partner"].create({"name": arabic_name})
        payment = self.init_payment(-200.0, post=False, partner=partner)
        payment.journal_id = self.journal
        payment.payment_method_line_id = self.outbound_payment_method_line
        payment.action_post()
        report = self.env.ref("account_check_print.action_report_check")
        html, _report_type = report._render_qweb_html(
            report.report_name, payment.ids, data={}
        )
        self._log_html_diagnostics(
            "test_arabic_text_renders_in_check_report",
            html,
            expected=arabic_name,
        )
        self.assertIn(
            arabic_name.encode("utf-8"),
            html,
            f"Arabic payee name missing from report HTML. diagnostics={get_check_print_font_diagnostics()}",
        )
        self.assertIn(
            b"Check Print DejaVu",
            html,
            f"Check font marker missing from Arabic report HTML. diagnostics={get_check_print_font_diagnostics()}",
        )
        self.assertEqual(payment.check_field_direction(arabic_name), "rtl")
