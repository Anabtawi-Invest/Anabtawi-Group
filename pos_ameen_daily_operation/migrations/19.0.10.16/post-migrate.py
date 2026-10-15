import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # Methods configured on a POS as the "advance application" method record the
    # deposit of an advance order when it is picked up.
    cr.execute(
        """
        UPDATE pos_payment_method pm
           SET daily_ops_report_type = 'advance_applied'
         WHERE COALESCE(pm.daily_ops_report_type, 'none') = 'none'
           AND pm.id IN (
               SELECT pos_advance_application_payment_method_id
                 FROM pos_config
                WHERE pos_advance_application_payment_method_id IS NOT NULL
           )
     RETURNING pm.id
        """
    )
    method_ids = [row[0] for row in cr.fetchall()]
    _logger.info("Daily ops mapping: payment methods set to advance_applied: %s", method_ids)
