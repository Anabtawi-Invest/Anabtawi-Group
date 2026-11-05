from odoo.tests.common import TransactionCase

from ..controllers.mobile_api import _as_float, _parse_bearer


class TestMobileAPIHelpers(TransactionCase):
    def test_parse_bearer(self):
        self.assertEqual(_parse_bearer("Bearer abc123"), "abc123")
        self.assertEqual(_parse_bearer("bearer token"), "token")
        self.assertIsNone(_parse_bearer("Basic token"))
        self.assertIsNone(_parse_bearer(""))

    def test_as_float(self):
        self.assertEqual(_as_float("31.95"), 31.95)
        self.assertIsNone(_as_float("not-a-number"))
        self.assertIsNone(_as_float(None))

