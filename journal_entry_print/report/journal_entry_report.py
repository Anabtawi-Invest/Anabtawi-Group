from odoo import _, api, models
from odoo.exceptions import UserError


class ReportJournalEntry(models.AbstractModel):
    _name = "report.journal_entry_print.report_journal_entry"
    _description = "Journal Entry PDF"

    @api.model
    def _format_analytic_distribution(self, distribution):
        """Return the analytic widget's account names and percentages."""
        if not distribution:
            return ""

        analytic_accounts = self.env["account.analytic.account"]
        parts = []
        for account_keys, percentage in distribution.items():
            try:
                account_ids = [
                    int(account_id)
                    for account_id in str(account_keys).split(",")
                    if account_id
                ]
            except ValueError:
                account_ids = []

            names = analytic_accounts.browse(account_ids).exists().mapped(
                "display_name"
            )
            account_label = ", ".join(names) or str(account_keys)
            parts.append(f"{account_label}: {percentage:g}%")
        return "; ".join(parts)

    @api.model
    def _format_reconciliation(self, line):
        details = []
        if line.matching_number:
            details.append(_("Matching: %s", line.matching_number))
        if line.full_reconcile_id:
            details.append(
                _("Full reconciliation: %s", line.full_reconcile_id.display_name)
            )
        elif line.matched_debit_ids or line.matched_credit_ids:
            details.append(_("Partially reconciled"))
        elif line.reconciled:
            details.append(_("Reconciled"))

        related_moves = [
            move_name
            for move_name in line.reconciled_lines_ids.mapped("move_name")
            if move_name
        ]
        if related_moves:
            details.append(
                _("Related entries: %s", ", ".join(dict.fromkeys(related_moves)))
            )
        return " · ".join(details)

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["account.move"].browse(docids).exists()
        invalid_moves = docs.filtered(lambda move: move.move_type != "entry")
        if invalid_moves:
            invalid_names = ", ".join(invalid_moves.mapped("display_name"))
            raise UserError(
                _(
                    "Journal Entry PDF can only print regular journal entries "
                    "(move type 'Journal Entry'). The following records are not "
                    "regular journal entries: %s",
                    invalid_names,
                )
            )

        lines_by_move = {
            move.id: move.line_ids.sorted(lambda line: (line.sequence, line.id))
            for move in docs
        }
        totals_by_move = {
            move.id: {
                "debit": sum(move.line_ids.mapped("debit")),
                "credit": sum(move.line_ids.mapped("credit")),
            }
            for move in docs
        }
        return {
            "doc_ids": docs.ids,
            "doc_model": "account.move",
            "docs": docs,
            "lines_by_move": lines_by_move,
            "totals_by_move": totals_by_move,
            "format_analytic_distribution": self._format_analytic_distribution,
            "format_reconciliation": self._format_reconciliation,
        }
