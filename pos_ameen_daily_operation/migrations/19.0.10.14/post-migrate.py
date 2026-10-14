import logging

_logger = logging.getLogger(__name__)

# One-time mapping of the delivery-app payment methods that were previously
# identified by hard-coded ids in the report code.
LEGACY_DELIVERY_METHODS = {
    142: 'talabat',
    143: 'careem',
    144: 'mythings',
    145: 'kabseh',
}

# Name keywords the POS dashboard used to detect employee debt methods.
EMPLOYEE_DEBT_KEYWORDS = ('%ذمم%', '%ذمة%', '%ذمه%', '%موظف%', '%employee%')


def migrate(cr, version):
    if not version:
        return

    for method_id, report_type in LEGACY_DELIVERY_METHODS.items():
        cr.execute(
            "SELECT daily_ops_report_type FROM pos_payment_method WHERE id = %s",
            (method_id,),
        )
        row = cr.fetchone()
        if not row:
            _logger.warning("Daily ops mapping: payment method %s not found, skipped", method_id)
            continue
        cr.execute(
            "UPDATE pos_payment_method SET daily_ops_report_type = %s WHERE id = %s",
            (report_type, method_id),
        )
        _logger.info(
            "Daily ops mapping: payment method %s set to %s (was %s)",
            method_id, report_type, row[0],
        )

    cr.execute(
        """
        UPDATE pos_payment_method
           SET daily_ops_report_type = 'employee_debt'
         WHERE COALESCE(daily_ops_report_type, 'none') = 'none'
           AND id NOT IN %s
           AND name::text ILIKE ANY (%s)
     RETURNING id
        """,
        (tuple(LEGACY_DELIVERY_METHODS), list(EMPLOYEE_DEBT_KEYWORDS)),
    )
    debt_ids = [row[0] for row in cr.fetchall()]
    _logger.info("Daily ops mapping: payment methods set to employee_debt: %s", debt_ids)
