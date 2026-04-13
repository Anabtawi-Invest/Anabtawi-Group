# -*- coding: utf-8 -*-
# Part of Creyox Technologies
from odoo import models, fields, api, _
from datetime import timedelta


class DirectPrintConfig(models.TransientModel):
    _inherit = "res.config.settings"

    job_retention_days = fields.Integer(
        related="company_id.job_retention_days", readonly=False
    )

    retention_policy = fields.Selection(
        related="company_id.retention_policy", readonly=False
    )

    @api.onchange("retention_policy")
    def _onchange_retention_policy(self):
        """Update job_retention_days based on retention_policy selection."""
        if self.retention_policy and self.retention_policy != "custom":
            self.job_retention_days = int(self.retention_policy)

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-generate print engine key at host system creation."""
        records = super(DirectPrintConfig, self).create(vals_list)
        for record in records:
            record._ensure_retention_cron()
        return records

    def action_cleanup_old_print_jobs(self):
        """Manually trigger cleanup of old print jobs for this report."""

        self.ensure_one()
        cutoff_date = fields.Datetime.now() - timedelta(days=self.job_retention_days)

        old_jobs = self.env["print.job"].search(
            [
                ("state", "in", ["done", "error", "cancelled"]),
                ("create_date", "<", cutoff_date),
            ]
        )
        if old_jobs:
            old_jobs.unlink()

    def _ensure_retention_cron(self):
        """
        Create or update scheduled action for print job retention cleanup.
        One cron per Print Engine Client.
        """
        self.ensure_one()

        if not self.job_retention_days or self.job_retention_days <= 0:
            return

        cron_name = f"Print Job Cleanup ({self.company_id.name})"

        cron = (
            self.env["ir.cron"]
            .sudo()
            .search(
                [
                    ("name", "=", cron_name),
                    ("model_id.model", "=", "res.config.settings"),
                ],
                limit=1,
            )
        )

        interval_number = self.job_retention_days
        interval_type = "days"

        vals = {
            "name": cron_name,
            "model_id": self.env.ref(
                "cr_all_in_one_direct_print.model_res_config_settings"
            ).id,
            "state": "code",
            "code": f"model.browse({self.id}).action_cleanup_old_print_jobs()",
            "interval_number": interval_number,
            "interval_type": interval_type,
            "active": True,
        }

        if cron:
            cron.write(vals)
        else:
            self.env["ir.cron"].create(vals)

    def write(self, vals):
        res = super().write(vals)

        if "job_retention_days" in vals or "retention_policy" in vals:
            for record in self:
                record._ensure_retention_cron()

        return res


class DirectPrintCompany(models.Model):
    _inherit = "res.company"

    job_retention_days = fields.Integer(
        string="Job Retention Period (Days)",
        help="How long to keep completed/failed jobs in the queue. "
        "Jobs older than this will be automatically deleted. ",
    )

    retention_policy = fields.Selection(
        [("7", "7 Days"), ("30", "30 Days"), ("90", "90 Days"), ("custom", "Custom")],
        string="Retention Policy",
        help="Automatically delete old jobs after specified period",
    )
