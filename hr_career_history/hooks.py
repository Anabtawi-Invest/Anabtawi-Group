from .models.hr_employee_career_history import (
    BACKFILL_CRON_XMLID,
    PARAM_BACKFILL_LAST_ID,
)


def post_init_hook(env):
    """Start the one-time backfill of the career ledger from existing versions.

    The work runs in batches through a cron, so installing the module on a
    live database stays fast and cannot time out.
    """
    env["ir.config_parameter"].sudo().set_param(PARAM_BACKFILL_LAST_ID, 0)
    cron = env.ref(BACKFILL_CRON_XMLID, raise_if_not_found=False)
    if cron:
        cron.sudo().active = True
        cron._trigger()
