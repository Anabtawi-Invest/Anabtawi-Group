def migrate(cr, version):
    """Force a clean re-registration when upgrading from legacy access-only tokens."""
    cr.execute(
        """
        UPDATE anabtawi_mobile_device
           SET active = FALSE,
               device_uid = NULL,
               token_index = NULL,
               token_hash = NULL,
               token_expires_at = NULL,
               refresh_token_index = NULL,
               refresh_token_hash = NULL,
               refresh_token_expires_at = NULL
        """
    )
