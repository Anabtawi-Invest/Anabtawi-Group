# -*- coding: utf-8 -*-
from datetime import datetime, time
import io

from odoo import _, api, fields, models


class PosUnifiedReportWizard(models.TransientModel):
    _name = "pos.unified.report.wizard"
    _description = "POS Unified Report & Export Wizard"

    date_from = fields.Date(
        string="Start Date",
        required=True,
        default=fields.Date.context_today,
    )
    date_to = fields.Date(
        string="End Date",
        required=True,
        default=fields.Date.context_today,
    )
    config_ids = fields.Many2many(
        "pos.config",
        string="POS Branches",
        help="Leave empty to include all active branches.",
    )

    def action_open_dashboard(self):
        self.ensure_one()
        c_ids = self.config_ids.ids if self.config_ids else []
        return {
            "type": "ir.actions.client",
            "tag": "pos_reporting_dashboard_main",
            "name": _("POS Executive Dashboard"),
            "params": {
                "date_from": fields.Date.to_string(self.date_from),
                "date_to": fields.Date.to_string(self.date_to),
                "config_ids": c_ids,
            },
        }

    def action_open_pivot(self):
        self.ensure_one()
        # 1. Clear previous transient report records
        self.env["pos.unified.report"].search([]).unlink()

        # 2. Populate unified report records
        dt_start = datetime.combine(self.date_from, time.min)
        dt_end = datetime.combine(self.date_to, time.max)
        str_start = fields.Datetime.to_string(dt_start)
        str_end = fields.Datetime.to_string(dt_end)

        config_domain = [("active", "=", True)]
        if self.config_ids:
            config_domain.append(("id", "in", self.config_ids.ids))
        configs = self.env["pos.config"].search(config_domain)
        active_config_ids = set(configs.ids)

        session_domain = [
            ("config_id", "in", list(active_config_ids)),
            "|",
            "&", ("start_at", ">=", str_start), ("start_at", "<=", str_end),
            "&", ("stop_at", ">=", str_start), ("stop_at", "<=", str_end),
        ]
        sessions = self.env["pos.session"].search(session_domain)
        session_ids = sessions.ids

        vals_list = []

        if session_ids:
            # POS Payments
            payments = self.env["pos.payment"].search([("session_id", "in", session_ids)])
            for pay in payments:
                amt = pay.amount or 0.0
                pm = pay.payment_method_id
                daily_type = getattr(pm, "daily_ops_report_type", "")
                pm_type = getattr(pm, "type", "")
                pm_name = (pm.name or "").lower()

                is_cash = daily_type == "cash" or pm_type == "cash" or "cash" in pm_name or "نقد" in pm_name
                is_visa = daily_type == "visa" or pm_type in ("bank", "pay_later") or "visa" in pm_name or "بطاقة" in pm_name or "card" in pm_name

                vals_list.append({
                    "name": pay.pos_order_id.name or pay.name or _("POS Payment"),
                    "date": pay.payment_date.date() if pay.payment_date else self.date_from,
                    "config_id": pay.session_id.config_id.id,
                    "session_id": pay.session_id.id,
                    "payment_method_id": pm.id,
                    "report_type": "pos_sales",
                    "amount": amt,
                    "cash_amount": amt if is_cash else 0.0,
                    "visa_amount": amt if is_visa else 0.0,
                    "partner_id": pay.pos_order_id.partner_id.id if pay.pos_order_id else False,
                })

            # Statement Lines (Cash In / Out)
            st_lines = self.env["account.bank.statement.line"].search([
                ("pos_session_id", "in", session_ids),
            ])
            for st in st_lines:
                amt = st.amount or 0.0
                is_in = amt > 0
                vals_list.append({
                    "name": st.payment_ref or st.ref or _("Cash Move"),
                    "date": st.date or self.date_from,
                    "config_id": st.pos_session_id.config_id.id,
                    "session_id": st.pos_session_id.id,
                    "report_type": "cash_in" if is_in else "cash_out",
                    "amount": abs(amt),
                    "cash_in_amount": amt if is_in else 0.0,
                    "cash_out_amount": abs(amt) if not is_in else 0.0,
                    "partner_id": st.partner_id.id,
                })

        # Pledges (Rahen In / Out)
        if "pos.advance.order.pledge" in self.env:
            pledges_adv = self.env["pos.advance.order.pledge"].search([
                "|",
                "&", ("pos_order_id", "!=", False),
                     ("pos_order_id.date_order", ">=", str_start),
                     ("pos_order_id.date_order", "<=", str_end),
                "&", ("order_id", "!=", False),
                     ("order_id.create_date", ">=", str_start),
                     ("order_id.create_date", "<=", str_end),
            ])
            for pledge in pledges_adv:
                cfg_id = False
                if pledge.pos_order_id:
                    cfg_id = pledge.pos_order_id.config_id.id
                elif pledge.order_id and hasattr(pledge.order_id, "pos_config_id"):
                    cfg_id = pledge.order_id.pos_config_id.id
                if not cfg_id or cfg_id not in active_config_ids:
                    continue

                amt = pledge.pledge_subtotal or getattr(pledge, "pledge_amount", 0.0) or 0.0
                is_in = pledge.state == "active"
                vals_list.append({
                    "name": pledge.display_name or _("Pledge Record"),
                    "date": pledge.create_date.date() if pledge.create_date else self.date_from,
                    "config_id": cfg_id,
                    "report_type": "rahen_in" if is_in else "rahen_out",
                    "amount": amt,
                    "rahen_in_amount": amt if is_in else 0.0,
                    "rahen_out_amount": amt if not is_in else 0.0,
                    "partner_id": pledge.partner_id.id if hasattr(pledge, "partner_id") else False,
                })

        # Advance Orders
        if "pos.advance.order" in self.env:
            adv_orders = self.env["pos.advance.order"].search([
                ("create_date", ">=", str_start),
                ("create_date", "<=", str_end),
                ("state", "not in", ("draft", "cancel")),
            ])
            for adv in adv_orders:
                cfg_id = adv.pos_config_id.id if adv.pos_config_id else (adv.from_pos_config_id.id if hasattr(adv, "from_pos_config_id") else False)
                if not cfg_id or cfg_id not in active_config_ids:
                    continue
                amt = adv.advance_amount or 0.0
                vals_list.append({
                    "name": adv.name or _("Advance Order"),
                    "date": adv.create_date.date() if adv.create_date else self.date_from,
                    "config_id": cfg_id,
                    "report_type": "advance_deposit",
                    "amount": amt,
                    "advance_amount": amt,
                    "partner_id": adv.partner_id.id if hasattr(adv, "partner_id") else False,
                })

        if vals_list:
            self.env["pos.unified.report"].create(vals_list)

        return {
            "name": _("Unified POS Operations Analysis"),
            "type": "ir.actions.act_window",
            "res_model": "pos.unified.report",
            "view_mode": "pivot,graph,list",
            "target": "current",
        }

    def action_export_xlsx(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/pos_unified_report/xlsx/{self.id}",
            "target": "self",
        }

    def _generate_xlsx_content(self):
        self.ensure_one()
        import xlsxwriter

        service = self.env["pos.reporting.dashboard"]
        config_ids = self.config_ids.ids if self.config_ids else None
        data = service.get_dashboard_data(
            date_from=fields.Date.to_string(self.date_from),
            date_to=fields.Date.to_string(self.date_to),
            config_ids=config_ids,
        )

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})

        # Styles
        title_fmt = workbook.add_format({"bold": True, "font_size": 16, "font_color": "#1A252C"})
        sub_fmt = workbook.add_format({"font_size": 11, "font_color": "#555555"})
        header_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#1F4E78",
            "font_color": "#FFFFFF",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
        })
        text_fmt = workbook.add_format({"border": 1, "align": "left"})
        total_text_fmt = workbook.add_format({"border": 1, "bold": True, "bg_color": "#E9ECEF"})
        num_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.000", "align": "right"})
        total_num_fmt = workbook.add_format({"border": 1, "bold": True, "num_format": "#,##0.000", "bg_color": "#E9ECEF", "align": "right"})

        # --- Worksheet 1: Executive Summary ---
        sheet1 = workbook.add_worksheet(_("Branch Executive Summary"))
        sheet1.write(0, 0, _("POS Unified Operations Report"), title_fmt)
        sheet1.write(1, 0, _("Period: %s to %s") % (data["date_from"], data["date_to"]), sub_fmt)

        headers = [
            _("Branch Name"),
            _("Total Sales"),
            _("Cash Sales"),
            _("Visa Sales"),
            _("Hospitality"),
            _("Talabat"),
            _("Careem"),
            _("Mythings"),
            _("Kabseh"),
            _("Cash In"),
            _("Cash Out"),
            _("Net Cash Moves"),
            _("Rahen In (Pledge)"),
            _("Rahen Out (Return)"),
            _("Net Pledges"),
            _("Advance Deposits"),
            _("Delivery Fees"),
        ]

        sheet1.set_column(0, 0, 26)
        for col_idx in range(1, len(headers)):
            sheet1.set_column(col_idx, col_idx, 15)

        start_row = 3
        for col_idx, h in enumerate(headers):
            sheet1.write(start_row, col_idx, h, header_fmt)

        curr_row = start_row + 1
        for b in data["branches"]:
            sheet1.write(curr_row, 0, b["branch_name"], text_fmt)
            sheet1.write_number(curr_row, 1, b["sales"], num_fmt)
            sheet1.write_number(curr_row, 2, b["cash"], num_fmt)
            sheet1.write_number(curr_row, 3, b["visa"], num_fmt)
            sheet1.write_number(curr_row, 4, b["hospitality"], num_fmt)
            sheet1.write_number(curr_row, 5, b["talabat"], num_fmt)
            sheet1.write_number(curr_row, 6, b["careem"], num_fmt)
            sheet1.write_number(curr_row, 7, b["mythings"], num_fmt)
            sheet1.write_number(curr_row, 8, b["kabseh"], num_fmt)
            sheet1.write_number(curr_row, 9, b["cash_in"], num_fmt)
            sheet1.write_number(curr_row, 10, b["cash_out"], num_fmt)
            sheet1.write_number(curr_row, 11, b["net_cash_moves"], num_fmt)
            sheet1.write_number(curr_row, 12, b["rahen_in"], num_fmt)
            sheet1.write_number(curr_row, 13, b["rahen_out"], num_fmt)
            sheet1.write_number(curr_row, 14, b["net_pledges"], num_fmt)
            sheet1.write_number(curr_row, 15, b["advance_deposits"], num_fmt)
            sheet1.write_number(curr_row, 16, b["delivery_amount"], num_fmt)
            curr_row += 1

        # Global Total Row
        gt = data["global_totals"]
        sheet1.write(curr_row, 0, _("TOTALS"), total_text_fmt)
        sheet1.write_number(curr_row, 1, gt["sales"], total_num_fmt)
        sheet1.write_number(curr_row, 2, gt["cash"], total_num_fmt)
        sheet1.write_number(curr_row, 3, gt["visa"], total_num_fmt)
        sheet1.write_number(curr_row, 4, gt["hospitality"], total_num_fmt)
        sheet1.write_number(curr_row, 5, gt["talabat"], total_num_fmt)
        sheet1.write_number(curr_row, 6, gt["careem"], total_num_fmt)
        sheet1.write_number(curr_row, 7, gt["mythings"], total_num_fmt)
        sheet1.write_number(curr_row, 8, gt["kabseh"], total_num_fmt)
        sheet1.write_number(curr_row, 9, gt["cash_in"], total_num_fmt)
        sheet1.write_number(curr_row, 10, gt["cash_out"], total_num_fmt)
        sheet1.write_number(curr_row, 11, gt["net_cash_moves"], total_num_fmt)
        sheet1.write_number(curr_row, 12, gt["rahen_in"], total_num_fmt)
        sheet1.write_number(curr_row, 13, gt["rahen_out"], total_num_fmt)
        sheet1.write_number(curr_row, 14, gt["net_pledges"], total_num_fmt)
        sheet1.write_number(curr_row, 15, gt["advance_deposits"], total_num_fmt)
        sheet1.write_number(curr_row, 16, gt["delivery_amount"], total_num_fmt)

        workbook.close()
        return output.getvalue()
