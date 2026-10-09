# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .classifier import PL_TYPES, classify_account


class CeoSmartScannerWizard(models.TransientModel):
    _name = "ceo.smart.scanner.wizard"
    _description = "Smart Scanner: classify accounts & analytic accounts"

    overwrite_existing = fields.Boolean(
        string="Refresh auto-classified rows",
        default=True,
        help="Re-apply the latest rules to everything the scanner classified before. "
        "Rows you changed by hand are never touched.",
    )

    # ------------------------------------------------------------------
    # Core scan (also used by the install hook and the dashboard itself)
    # ------------------------------------------------------------------
    @api.model
    def _scan(self, overwrite=True):
        Bucket = self.env["ceo.cost.bucket"].sudo().with_context(active_test=False)
        buckets = {b.code: b.id for b in Bucket.search([])}
        if not buckets:
            raise UserError(_("No cost buckets found. Please update the module to load the initial data."))

        ctx = self.with_context(ecd_scan=True, active_test=False)
        Mapping = ctx.env["ceo.cost.account.mapping"].sudo()
        existing = {m.account_id.id: m for m in Mapping.search([])}
        accounts = ctx.env["account.account"].sudo().search([("account_type", "in", PL_TYPES)])
        labels = Mapping._account_info(accounts)

        to_create, updated = [], 0
        for acc in accounts:
            code, name = labels[acc.id]
            bucket_id = buckets.get(classify_account(code, name, acc.account_type))
            if not bucket_id:
                continue
            current = existing.get(acc.id)
            if not current:
                to_create.append({"bucket_id": bucket_id, "account_id": acc.id, "auto": True})
            elif overwrite and current.auto and current.bucket_id.id != bucket_id:
                current.write({"bucket_id": bucket_id})
                updated += 1
        if to_create:
            Mapping.create(to_create)

        # Analytic accounts -> branch / factory / department
        AnalyticMap = ctx.env["ceo.cost.analytic.map"].sudo()
        known = {m.analytic_id.id: m for m in AnalyticMap.with_context(active_test=False).search([])}
        analytics = ctx.env["account.analytic.account"].sudo().search([])
        a_create, a_updated = [], 0
        for analytic in analytics:
            vals = AnalyticMap._classify(analytic)
            current = known.get(analytic.id)
            if not current:
                a_create.append(dict(vals, analytic_id=analytic.id, auto=True, active=vals["kind"] != "other"))
            elif overwrite and current.auto:
                changes = {k: v for k, v in vals.items() if current[k] != v}
                if changes:
                    current.write(changes)
                    a_updated += 1
        if a_create:
            AnalyticMap.create(a_create)

        return {
            "accounts_created": len(to_create),
            "accounts_updated": updated,
            "analytics_created": len(a_create),
            "analytics_updated": a_updated,
        }

    def action_run_smart_scan(self):
        self.ensure_one()
        res = self._scan(self.overwrite_existing)
        message = _(
            "Accounts: %(ac)s new, %(au)s refreshed. Analytic accounts: %(nc)s new, %(nu)s refreshed.",
            ac=res["accounts_created"],
            au=res["accounts_updated"],
            nc=res["analytics_created"],
            nu=res["analytics_updated"],
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Smart Scan completed"),
                "message": message,
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
