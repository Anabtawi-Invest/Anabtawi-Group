# -*- coding: utf-8 -*-
import base64
import io
from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError

try:
    import xlsxwriter
except ImportError:  # pragma: no cover
    xlsxwriter = None


class PosDeliveryCashExcelWizard(models.TransientModel):
    _name = "pos.delivery.cash.excel.wizard"
    _description = "Export Cash vs Closing Delivery Excel"

    date_from = fields.Date(
        string="From Date",
        required=True,
        default=lambda self: fields.Date.context_today(self),
    )
    date_to = fields.Date(
        string="To Date",
        required=True,
        default=lambda self: fields.Date.context_today(self),
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    pos_config_ids = fields.Many2many(
        "pos.config",
        string="Points of Sale",
        domain="[('company_id', '=', company_id)]",
        help="Leave empty to include all POS for the company.",
    )
    file_data = fields.Binary(string="File", readonly=True)
    filename = fields.Char(string="Filename", readonly=True)

    def action_export_xlsx(self):
        self.ensure_one()
        if xlsxwriter is None:
            raise UserError(_("The Python library 'xlsxwriter' is required to export Excel files."))
        if self.date_from > self.date_to:
            raise UserError(_("From Date cannot be after To Date."))

        rows = self._prepare_rows()
        if not rows:
            raise UserError(_("No closed POS sessions found for the selected filters."))

        xlsx_bytes = self._build_xlsx(rows)
        fname = "Cash_vs_Closing_Delivery_%s_%s.xlsx" % (self.date_from, self.date_to)
        self.write(
            {
                "file_data": base64.b64encode(xlsx_bytes),
                "filename": fname,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": (
                "/web/content/?model=%s&id=%s&field=file_data&filename=%s&download=true"
                % (self._name, self.id, fname)
            ),
            "target": "self",
        }

    def _prepare_session_domain(self):
        self.ensure_one()
        domain = [
            ("state", "=", "closed"),
            ("company_id", "=", self.company_id.id),
            ("start_at", ">=", fields.Datetime.to_datetime(self.date_from)),
            ("start_at", "<", fields.Datetime.to_datetime(self.date_to + timedelta(days=1))),
        ]
        if self.pos_config_ids:
            domain.append(("config_id", "in", self.pos_config_ids.ids))
        return domain

    def _get_cash_sales_amount(self, session):
        cash_payment_method = session.payment_method_ids.filtered("is_cash_count")[:1]
        if not cash_payment_method:
            return 0.0
        domain = session._get_captured_payments_domain() + [
            ("payment_method_id", "=", cash_payment_method.id)
        ]
        result = self.env["pos.payment"]._read_group(domain, aggregates=["amount:sum"])
        return result[0][0] or 0.0

    def _get_cash_in_out_amounts(self, session):
        statement_lines = session.sudo().statement_line_ids
        if session.state == "closed" and session.cash_real_transaction and not statement_lines:
            # Fallback if statement lines were cleaned: only net is available.
            net = session.cash_real_transaction or 0.0
            return (max(net, 0.0), min(net, 0.0), net)

        cash_in = sum(line.amount for line in statement_lines if line.amount > 0)
        cash_out = sum(line.amount for line in statement_lines if line.amount < 0)
        if session.state == "closed":
            net = session.cash_real_transaction or (cash_in + cash_out)
        else:
            net = cash_in + cash_out
        return cash_in, cash_out, net

    def _prepare_rows(self):
        self.ensure_one()
        sessions = self.env["pos.session"].search(
            self._prepare_session_domain(),
            order="start_at asc, id asc",
        )
        rows = []
        for session in sessions:
            currency = session.currency_id
            opening = currency.round(session.cash_register_balance_start or 0.0)
            cash_sales = currency.round(self._get_cash_sales_amount(session))
            cash_in, cash_out, cash_in_out = self._get_cash_in_out_amounts(session)
            cash_in = currency.round(cash_in)
            cash_out = currency.round(cash_out)
            cash_in_out = currency.round(cash_in_out)
            session_delivery = currency.round(session._get_session_delivered_total())
            cash_on_system = currency.round(session.cash_register_balance_end or 0.0)
            closing_delivery = currency.round(session._get_closing_delivered_total())
            rows.append(
                {
                    "date": fields.Date.to_date(session.start_at) if session.start_at else "",
                    "session": session.name or "",
                    "pos": session.config_id.name or "",
                    "opening": opening,
                    "cash_sales": cash_sales,
                    "cash_in": cash_in,
                    "cash_out": cash_out,
                    "cash_in_out": cash_in_out,
                    "session_delivery": session_delivery,
                    "cash_on_system": cash_on_system,
                    "closing_delivery": closing_delivery,
                    "difference": currency.round(cash_on_system - closing_delivery),
                    "currency": currency.name or "",
                }
            )
        return rows

    def _build_xlsx(self, rows):
        self.ensure_one()
        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
        sheet = workbook.add_worksheet(_("Cash vs Closing Delivery"))

        title_fmt = workbook.add_format({"bold": True, "font_size": 14})
        note_fmt = workbook.add_format({"italic": True})
        header_fmt = workbook.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1})
        text_fmt = workbook.add_format({"border": 1})
        date_fmt = workbook.add_format({"border": 1, "num_format": "yyyy-mm-dd"})
        money_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.00"})
        total_label_fmt = workbook.add_format({"bold": True, "border": 1})
        total_money_fmt = workbook.add_format({"bold": True, "border": 1, "num_format": "#,##0.00"})

        sheet.write(0, 0, _("Cash on System vs Closing Delivery Amount"), title_fmt)
        sheet.write(1, 0, _("Company: %s", self.company_id.name))
        sheet.write(2, 0, _("Period: %s → %s", self.date_from, self.date_to))
        sheet.write(
            3,
            0,
            _(
                "Cash on System = Opening + Cash Sales + Cash In/Out - Delivery During Session"
            ),
            note_fmt,
        )

        headers = [
            _("Date"),
            _("Session"),
            _("Point of Sale"),
            _("Opening Cash"),
            _("Cash Sales"),
            _("Cash In"),
            _("Cash Out"),
            _("Cash In/Out"),
            _("Delivery During Session"),
            _("Cash on System"),
            _("Closing Delivery Amount"),
            _("Difference"),
            _("Currency"),
        ]
        money_keys = [
            "opening",
            "cash_sales",
            "cash_in",
            "cash_out",
            "cash_in_out",
            "session_delivery",
            "cash_on_system",
            "closing_delivery",
            "difference",
        ]

        for col, header in enumerate(headers):
            sheet.write(5, col, header, header_fmt)

        totals = {key: 0.0 for key in money_keys}
        for index, row in enumerate(rows):
            line = 6 + index
            sheet.write(line, 0, row["date"] or "", date_fmt)
            sheet.write(line, 1, row["session"], text_fmt)
            sheet.write(line, 2, row["pos"], text_fmt)
            for offset, key in enumerate(money_keys):
                sheet.write_number(line, 3 + offset, row[key], money_fmt)
                totals[key] += row[key]
            sheet.write(line, 3 + len(money_keys), row["currency"], text_fmt)

        total_row = 6 + len(rows)
        sheet.write(total_row, 0, _("Total"), total_label_fmt)
        sheet.write(total_row, 1, "", total_label_fmt)
        sheet.write(total_row, 2, "", total_label_fmt)
        for offset, key in enumerate(money_keys):
            sheet.write_number(total_row, 3 + offset, totals[key], total_money_fmt)
        sheet.write(total_row, 3 + len(money_keys), "", total_label_fmt)

        sheet.set_column(0, 0, 14)
        sheet.set_column(1, 2, 22)
        sheet.set_column(3, 11, 20)
        sheet.set_column(12, 12, 12)

        workbook.close()
        return buffer.getvalue()
