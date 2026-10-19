from odoo import _, fields, models
from odoo.exceptions import UserError

PROTECTED_REPORT_TYPES = ('talabat', 'careem', 'mythings', 'kabseh')


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    daily_ops_report_type = fields.Selection(
        selection=[
            ('none', 'None'),
            ('cash', 'Cash'),
            ('visa', 'Visa'),
            ('hospitality', 'Hospitality'),
            ('talabat', 'Talabat'),
            ('careem', 'Careem'),
            ('mythings', 'Mythings'),
            ('kabseh', 'Kabseh'),
            ('employee_debt', 'Employee Debt'),
            ('advance_applied', 'Advance Applied'),
        ],
        string='Daily Operations Report Type',
        help=(
            'Column of the Daily Operations report and POS dashboard that receives the '
            'payments of this method. Hospitality and Advance Applied (advance order deposits '
            'used at pickup) payments are excluded from Sales; None and Employee Debt are '
            'included in Sales without a dedicated Excel column.'
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
        protected = self.filtered(lambda method: method.daily_ops_report_type in PROTECTED_REPORT_TYPES)
        if protected:
            names = ', '.join(protected.mapped('name'))
            raise UserError(
                _('The following payment methods are protected and cannot be deleted: %s') % names
            )
        return super().unlink()
