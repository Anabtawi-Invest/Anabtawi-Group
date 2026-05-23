# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PosPurgeReportLine(models.TransientModel):
    _name = "pos.purge.report.line"
    _description = "POS Purge Dry-Run Report Line"
    _order = "level desc, id"

    wizard_id = fields.Many2one("pos.purge.wizard", required=True, ondelete="cascade")
    level = fields.Selection(
        [("info", "Info"), ("warning", "Warning"), ("error", "Error")],
        default="info",
        required=True,
    )
    category = fields.Char()
    message = fields.Text(required=True)
    order_id = fields.Many2one("pos.order", readonly=True)


class PosPurgeWizard(models.TransientModel):
    _name = "pos.purge.wizard"
    _description = "POS Historical Purge Wizard"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    cutoff_date = fields.Date(
        required=True,
        help="All POS orders with date_order strictly before this date (company timezone midnight) are in scope.",
    )
    state_preset = fields.Selection(
        [
            ("all", "All statuses"),
            ("safe", "Draft & cancelled only"),
            ("posted", "Paid & posted only"),
            ("custom", "Custom selection"),
        ],
        string="Status preset",
        default="all",
        required=True,
    )
    include_state_draft = fields.Boolean(string="New (draft)", default=True)
    include_state_cancel = fields.Boolean(string="Cancelled", default=True)
    include_state_paid = fields.Boolean(string="Paid", default=True)
    include_state_done = fields.Boolean(string="Posted (done)", default=True)
    mode = fields.Selection(
        [("dry_run", "Dry run (analysis only)"), ("purge", "Execute purge")],
        default="dry_run",
        required=True,
    )
    stock_handling = fields.Selection(
        [
            ("reverse", "Reverse done pickings (return)"),
            ("skip", "Detach pickings only (not recommended)"),
            ("block", "Block if done pickings exist"),
        ],
        default="reverse",
        required=True,
    )
    purge_sessions = fields.Boolean(
        string="Purge empty closed sessions",
        default=True,
        help="After deleting orders, remove closed sessions that have no remaining orders "
             "(only sessions fully before cutoff).",
    )
    block_submitted_einvoices = fields.Boolean(
        string="Block submitted e-invoices (JoFotara)",
        default=True,
        help="When enabled, orders whose invoice was sent to Jordan JoFotara (Jo Fawtara) "
             "or other government e-invoicing cannot be purged. Requires l10n_jo_edi for Jordan.",
    )
    ignore_blockers = fields.Boolean(
        string="Ignore blocking errors",
        default=False,
        help="Dangerous. Proceed despite JoFotara / open session / other blocking errors.",
    )
    stop_on_error = fields.Boolean(default=True)
    batch_size = fields.Integer(default=50)
    confirm_purge = fields.Boolean(
        string="I confirm this is irreversible",
        help="Required before executing purge.",
    )

    report_line_ids = fields.One2many("pos.purge.report.line", "wizard_id", readonly=True)
    state = fields.Selection(
        [("draft", "Draft"), ("analyzed", "Analyzed")],
        default="draft",
    )

    order_count = fields.Integer(readonly=True)
    session_count = fields.Integer(readonly=True)
    full_session_count = fields.Integer(readonly=True)
    mixed_session_count = fields.Integer(readonly=True)
    invoice_count = fields.Integer(readonly=True)
    picking_count = fields.Integer(readonly=True)
    done_picking_count = fields.Integer(readonly=True)
    error_count = fields.Integer(readonly=True)
    warning_count = fields.Integer(readonly=True)

    @api.onchange("state_preset")
    def _onchange_state_preset(self):
        presets = {
            "all": (True, True, True, True),
            "safe": (True, True, False, False),
            "posted": (False, False, True, True),
        }
        if self.state_preset in presets:
            (
                self.include_state_draft,
                self.include_state_cancel,
                self.include_state_paid,
                self.include_state_done,
            ) = presets[self.state_preset]

    def _get_order_states(self):
        self.ensure_one()
        mapping = [
            ("draft", self.include_state_draft),
            ("cancel", self.include_state_cancel),
            ("paid", self.include_state_paid),
            ("done", self.include_state_done),
        ]
        return [state for state, enabled in mapping if enabled]

    def _purge_options(self):
        return {
            "stock_handling": self.stock_handling,
            "block_submitted_einvoices": self.block_submitted_einvoices,
            "ignore_blockers": self.ignore_blockers,
            "stop_on_error": self.stop_on_error,
            "batch_size": max(1, self.batch_size),
            "purge_sessions": self.purge_sessions,
            "order_states": self._get_order_states(),
        }

    def action_analyze(self):
        self.ensure_one()
        if not self.cutoff_date:
            raise UserError(_("Set a cutoff date."))
        if not self._get_order_states():
            raise UserError(_("Select at least one POS order status to include."))

        service = self.env["pos.purge.service"]
        result = service.dry_run(self.company_id, self.cutoff_date, self._purge_options())

        self.report_line_ids.unlink()
        lines = []
        stats = result["stats"]
        state_lines = ", ".join(
            _("%(label)s: %(count)s", label=info["label"], count=info["count"])
            for info in stats.get("state_breakdown", {}).values()
        ) or _("none")
        lines.append((0, 0, {
            "level": "info",
            "category": "summary",
            "message": _(
                "Scope: %(orders)s orders (%(states)s), %(sessions)s sessions "
                "(%(full)s fully purgeable, %(mixed)s mixed). "
                "%(inv)s invoices, %(pick)s pickings (%(done)s done).",
                orders=stats["order_count"],
                states=state_lines,
                sessions=stats["session_count"],
                full=stats["full_session_count"],
                mixed=stats["mixed_session_count"],
                inv=stats["invoice_count"],
                pick=stats["picking_count"],
                done=stats["done_picking_count"],
            ),
        }))
        for blocker in result["blockers"]:
            lines.append((0, 0, {
                "level": blocker["level"],
                "category": blocker.get("category"),
                "message": blocker["message"],
                "order_id": blocker.get("order_id") or False,
            }))

        errors = sum(1 for b in result["blockers"] if b["level"] == "error")
        warnings = sum(1 for b in result["blockers"] if b["level"] == "warning")

        self.write({
            "report_line_ids": lines,
            "state": "analyzed",
            "order_count": stats["order_count"],
            "session_count": stats["session_count"],
            "full_session_count": stats["full_session_count"],
            "mixed_session_count": stats["mixed_session_count"],
            "invoice_count": stats["invoice_count"],
            "picking_count": stats["picking_count"],
            "done_picking_count": stats["done_picking_count"],
            "error_count": errors,
            "warning_count": warnings,
        })

        return self._reopen_wizard()

    def action_execute_purge(self):
        self.ensure_one()
        if self.mode != "purge":
            raise UserError(_("Set mode to 'Execute purge'."))
        if not self._get_order_states():
            raise UserError(_("Select at least one POS order status to include."))
        if not self.confirm_purge:
            raise UserError(_("Check the confirmation box before executing purge."))
        if self.state != "analyzed":
            self.action_analyze()
        if self.error_count and not self.ignore_blockers:
            raise UserError(
                _("Cannot purge: %(n)s blocking error(s). Run dry-run or enable ignore blockers.", n=self.error_count)
            )

        service = self.env["pos.purge.service"]
        result = service.run_purge(self.company_id, self.cutoff_date, self._purge_options())

        ok = sum(1 for row in result["log"] if row.get("status") == "ok")
        err = sum(1 for row in result["log"] if row.get("status") == "error")
        sess = sum(1 for row in result["log"] if row.get("status") == "session_ok")

        message = _("Purged %(ok)s orders.", ok=ok)
        if sess:
            message += _(" Removed %(sess)s sessions.", sess=sess)
        if err:
            message += _(" %(err)s error(s) — see server log.", err=err)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("POS purge complete"),
                "message": message,
                "type": "success" if not err else "warning",
                "sticky": bool(err),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def _reopen_wizard(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "pos.purge.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
