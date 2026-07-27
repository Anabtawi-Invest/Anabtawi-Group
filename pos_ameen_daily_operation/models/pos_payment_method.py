from odoo import _, fields, models
from odoo.exceptions import UserError

PROTECTED_PAYMENT_METHOD_IDS = {142, 143, 144, 145}


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    daily_ops_report_type = fields.Selection(
        selection=[
            ('none', 'None'),
            ('cash', 'Cash'),
            ('visa', 'Visa'),
            ('hospitality', 'Hospitality'),
        ],
        string='Daily Operations Report Type',
        help=(
            'Choose None if this payment method should not appear in the '
            'Cash, Visa, or Hospitality columns of the Daily Operations report.'
        ),
    )

    def _is_write_forbidden(self, fields):
        whitelisted_fields = {'daily_ops_report_type'}
        remaining_fields = set(fields) - whitelisted_fields
        if not remaining_fields:
            return False
        return super()._is_write_forbidden(remaining_fields)

    def init(self):
        self.env.cr.execute(
            """
            UPDATE pos_payment_method
               SET daily_ops_report_type = 'none'
             WHERE daily_ops_report_type IS NULL
            """
        )
        self.env.cr.execute(
            """
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'pos_payment_method'
               AND column_name = 'is_cash'
             LIMIT 1
            """
        )
        if not self.env.cr.fetchone():
            return
        self.env.cr.execute(
            """
            UPDATE pos_payment_method
               SET daily_ops_report_type = CASE
                   WHEN is_cash THEN 'cash'
                   WHEN is_visa THEN 'visa'
                   WHEN is_hospitality THEN 'hospitality'
                   ELSE daily_ops_report_type
               END
             WHERE daily_ops_report_type IS NULL
               AND (is_cash OR is_visa OR is_hospitality)
            """
        )

    def unlink(self):
        protected = self.filtered(lambda method: method.id in PROTECTED_PAYMENT_METHOD_IDS)
        if protected:
            names = ', '.join(protected.mapped('name'))
            raise UserError(
                _('The following payment methods are protected and cannot be deleted: %s') % names
            )
        return super().unlink()
