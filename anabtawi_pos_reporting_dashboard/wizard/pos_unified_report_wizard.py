# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta
import io
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class PosUnifiedReportWizard(models.TransientModel):
    _name = "pos.unified.report.wizard"
    _description = "POS Unified Report & Export Wizard"

    def _default_date_from(self):
        today = fields.Date.context_today(self)
        return datetime.combine(today, time(6, 0, 0))

    def _default_date_to(self):
        today = fields.Date.context_today(self)
        tomorrow = today + timedelta(days=1)
        return datetime.combine(tomorrow, time(5, 0, 0))

    date_from = fields.Datetime(
        string="Start Date & Time",
        required=True,
        default=_default_date_from,
    )
    date_to = fields.Datetime(
        string="End Date & Time",
        required=True,
        default=_default_date_to,
    )
    config_ids = fields.Many2many(
        "pos.config",
        domain=[
            ("active", "=", True),
            ("name", "not ilike", "كافيه"),
            ("name", "not ilike", "نجيب"),
            ("name", "not ilike", "ذوابي"),
        ],
        string="POS Branches",
        help="Leave empty to include all active branches.",
    )

    def _to_datetime(self, val):
        if not val:
            return None
        if isinstance(val, datetime):
            return val
        val_str = str(val).strip().replace("T", " ")
        try:
            return datetime.strptime(val_str.split(".")[0], "%Y-%m-%d %H:%M:%S")
        except Exception:
            try:
                return fields.Datetime.from_string(val_str)
            except Exception:
                return None

    def action_open_dashboard(self):
        self.ensure_one()
        c_ids = self.config_ids.ids if self.config_ids else []
        return {
            "type": "ir.actions.client",
            "tag": "pos_reporting_dashboard_main",
            "name": _("POS Executive Dashboard"),
            "params": {
                "date_from": fields.Datetime.to_string(self.date_from),
                "date_to": fields.Datetime.to_string(self.date_to),
                "config_ids": c_ids,
            },
        }

    def action_open_pivot(self):
        self.ensure_one()
        c_ids = self.config_ids.ids if self.config_ids else None
        res = self.env["pos.reporting.dashboard"].open_kpi_drilldown(
            metric_type="sales",
            date_from=fields.Datetime.to_string(self.date_from),
            date_to=fields.Datetime.to_string(self.date_to),
            config_ids=c_ids,
        )
        res["view_mode"] = "pivot,graph,list"
        res["views"] = [
            (self.env.ref("anabtawi_pos_reporting_dashboard.view_pos_unified_report_pivot").id, "pivot"),
            (self.env.ref("anabtawi_pos_reporting_dashboard.view_pos_unified_report_graph").id, "graph"),
            (self.env.ref("anabtawi_pos_reporting_dashboard.view_pos_unified_report_tree").id, "list"),
        ]
        return res

    def action_export_xlsx(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/pos_unified_report/xlsx/{self.id}",
            "target": "new",
        }

    def _generate_xlsx_content(self):
        self.ensure_one()
        import xlsxwriter

        dt_start = self._to_datetime(self.date_from) or datetime.combine(fields.Date.context_today(self), time.min)
        dt_end = self._to_datetime(self.date_to) or datetime.combine(fields.Date.context_today(self), time.max)
        str_start = fields.Datetime.to_string(dt_start)
        str_end = fields.Datetime.to_string(dt_end)

        service = self.env["pos.reporting.dashboard"]
        config_ids = self.config_ids.ids if self.config_ids else None
        data = service.get_dashboard_data(
            date_from=str_start,
            date_to=str_end,
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
        center_fmt = workbook.add_format({"border": 1, "align": "center"})
        total_text_fmt = workbook.add_format({"border": 1, "bold": True, "bg_color": "#E9ECEF"})
        num_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.000", "align": "right"})
        total_num_fmt = workbook.add_format({"border": 1, "bold": True, "num_format": "#,##0.000", "bg_color": "#E9ECEF", "align": "right"})
        int_fmt = workbook.add_format({"border": 1, "num_format": "#,##0", "align": "right"})
        total_int_fmt = workbook.add_format({"border": 1, "bold": True, "num_format": "#,##0", "bg_color": "#E9ECEF", "align": "right"})

        # --- Sheet 1: Executive Summary ---
        sheet1 = workbook.add_worksheet(_("Branch Executive Summary"))
        sheet1.write(0, 0, _("POS Unified Operations Report"), title_fmt)
        sheet1.write(1, 0, _("Period: %s to %s") % (str_start, str_end), sub_fmt)

        # (header, data key, is_integer)
        summary_columns = [
            (_("Total Sales (Gross)"), "sales", False),
            (_("Orders / Min"), "orders_per_min", False),
            (_("Sales Without Tax"), "untaxed_sales", False),
            (_("Tax Amount"), "tax_amount", False),
            (_("Total Discounts"), "discount_amount", False),
            (_("Cash Sales"), "cash", False),
            (_("Visa Sales"), "visa", False),
            (_("Online & Delivery Sales"), "online_sales", False),
            (_("Debt Sales (مبيعات الذمم)"), "employee_debt", False),
            (_("Hospitality"), "hospitality", False),
            (_("Talabat"), "talabat", False),
            (_("Careem"), "careem", False),
            (_("Mythings"), "mythings", False),
            (_("Kabseh"), "kabseh", False),
            (_("Cash In"), "cash_in", False),
            (_("Cash Out"), "cash_out", False),
            (_("Net Cash Moves"), "net_cash_moves", False),
            (_("Pledge (Rahen) In"), "rahen_in", False),
            (_("Pledge (Rahen) Out"), "rahen_out", False),
            (_("Net Pledges"), "net_pledges", False),
            (_("Pledge Cash In"), "pledge_cash_in", False),
            (_("Pledge Cash Out"), "pledge_cash_out", False),
            (_("Pledge Cash Net"), "pledge_cash_net", False),
            (_("Pledge Visa In"), "pledge_visa_in", False),
            (_("Pledge Visa Out"), "pledge_visa_out", False),
            (_("Pledge Visa Net"), "pledge_visa_net", False),
            (_("Advance Deposits (Origin)"), "advance_deposits", False),
            (_("Advance Cash"), "advance_cash", False),
            (_("Advance Visa"), "advance_visa", False),
            (_("Scheduled Pickup Value"), "advance_pickup_value", False),
            (_("Pending Pickups"), "advance_pending_count", True),
            (_("Delivery Fees"), "delivery_amount", False),
            (_("Attendant Staff"), "attendant_employee_count", True),
            (_("Daily Labor Cost"), "total_labor_cost", False),
            (_("Extra Hours (hrs)"), "extra_hours", False),
        ]

        sheet1.set_column(0, 0, 28)
        sheet1.set_column(1, len(summary_columns), 16)

        start_row = 3
        sheet1.write(start_row, 0, _("Branch Name"), header_fmt)
        for col_idx, (header, _key, _is_int) in enumerate(summary_columns, start=1):
            sheet1.write(start_row, col_idx, header, header_fmt)

        curr_row = start_row + 1
        for b in data["branches"]:
            sheet1.write(curr_row, 0, b["branch_name"], text_fmt)
            for col_idx, (_header, key, is_int) in enumerate(summary_columns, start=1):
                sheet1.write_number(curr_row, col_idx, b.get(key, 0) or 0, int_fmt if is_int else num_fmt)
            curr_row += 1

        # Global Total Row Sheet 1
        gt = data["global_totals"]
        sheet1.write(curr_row, 0, _("TOTALS"), total_text_fmt)
        for col_idx, (_header, key, is_int) in enumerate(summary_columns, start=1):
            sheet1.write_number(curr_row, col_idx, gt.get(key, 0) or 0, total_int_fmt if is_int else total_num_fmt)

        # Target branch config IDs set
        target_config_ids = set(self.config_ids.ids) if self.config_ids else None

        # --- Sheet 2: Advance Orders Detail ---
        if "pos.advance.order" in self.env:
            sheet2 = workbook.add_worksheet(_("Advance Orders Detail"))
            sheet2.write(0, 0, _("POS Advance Orders Audit List"), title_fmt)
            sheet2.write(1, 0, _("Period: %s to %s") % (str_start, str_end), sub_fmt)

            adv_headers = [
                _("Reference"),
                _("Order Date & Time"),
                _("Scheduled Pickup Date & Time"),
                _("Customer"),
                _("Employee / Staff"),
                _("Deposit Branch (Origin)"),
                _("Pickup Branch (Target)"),
                _("Status"),
                _("Total Amount"),
                _("Advance Deposit Paid"),
                _("Remaining Balance"),
                _("Pledge Amount"),
                _("Deposit Payment Method"),
                _("Deposit Cash"),
                _("Deposit Visa"),
            ]

            sheet2.set_column(0, 0, 20)
            sheet2.set_column(1, 2, 22)
            sheet2.set_column(3, 4, 24)
            sheet2.set_column(5, 6, 24)
            sheet2.set_column(7, 7, 16)
            sheet2.set_column(8, 11, 18)
            sheet2.set_column(12, 12, 22)
            sheet2.set_column(13, 14, 18)

            start_row_adv = 3
            for col_idx, h in enumerate(adv_headers):
                sheet2.write(start_row_adv, col_idx, h, header_fmt)

            adv_recs = self.env["pos.advance.order"].sudo().search([("state", "not in", ("draft", "cancel"))], order="id desc")

            c_row = start_row_adv + 1
            tot_grand = 0.0
            tot_dep = 0.0
            tot_rem = 0.0
            tot_plg = 0.0
            tot_dep_cash = 0.0
            tot_dep_visa = 0.0

            for a in adv_recs:
                orig_cfg_id = a.from_pos_config_id.id if a.from_pos_config_id else (a.pos_config_id.id if a.pos_config_id else False)
                pick_cfg_id = a.pos_config_id.id if a.pos_config_id else orig_cfg_id

                if target_config_ids:
                    if (orig_cfg_id not in target_config_ids) and (pick_cfg_id not in target_config_ids):
                        continue

                c_dt = self._to_datetime(a.create_date)
                p_dt = self._to_datetime(a.picking_date)

                c_in_range = c_dt and (dt_start <= c_dt <= dt_end)
                p_in_range = p_dt and (dt_start <= p_dt <= dt_end)

                if not (c_in_range or p_in_range):
                    continue

                orig_name = a.from_pos_config_id.name if a.from_pos_config_id else (a.pos_config_id.name if a.pos_config_id else "")
                pick_name = a.pos_config_id.name if a.pos_config_id else orig_name
                emp_name = a.employee_id.name if a.employee_id else (a.user_id.name if a.user_id else "")
                state_label = dict(a._fields["state"].selection).get(a.state, a.state)

                g_amt = a.amount_grand_total or a.amount_total or 0.0
                d_amt = a.advance_amount or 0.0
                r_amt = a.amount_remaining or 0.0
                p_amt = a.pledge_amount or 0.0

                sheet2.write(c_row, 0, a.name or "", text_fmt)
                sheet2.write(c_row, 1, fields.Datetime.to_string(c_dt) if c_dt else "", center_fmt)
                sheet2.write(c_row, 2, fields.Datetime.to_string(p_dt) if p_dt else "", center_fmt)
                sheet2.write(c_row, 3, a.partner_id.name if a.partner_id else "", text_fmt)
                sheet2.write(c_row, 4, emp_name, text_fmt)
                sheet2.write(c_row, 5, orig_name, text_fmt)
                sheet2.write(c_row, 6, pick_name, text_fmt)
                sheet2.write(c_row, 7, state_label, center_fmt)
                sheet2.write_number(c_row, 8, g_amt, num_fmt)
                sheet2.write_number(c_row, 9, d_amt, num_fmt)
                sheet2.write_number(c_row, 10, r_amt, num_fmt)
                sheet2.write_number(c_row, 11, p_amt, num_fmt)

                channel = service._advance_channel(a)
                dep_cash = d_amt if channel == "cash" else 0.0
                dep_visa = d_amt if channel == "visa" else 0.0
                pm_label = a.pos_payment_method_id.name if a.pos_payment_method_id else (channel or "").capitalize()
                sheet2.write(c_row, 12, pm_label, text_fmt)
                sheet2.write_number(c_row, 13, dep_cash, num_fmt)
                sheet2.write_number(c_row, 14, dep_visa, num_fmt)

                tot_grand += g_amt
                tot_dep += d_amt
                tot_rem += r_amt
                tot_plg += p_amt
                tot_dep_cash += dep_cash
                tot_dep_visa += dep_visa
                c_row += 1

            # Total Row Sheet 2
            sheet2.write(c_row, 0, _("TOTALS"), total_text_fmt)
            for col in range(1, 8):
                sheet2.write(c_row, col, "", total_text_fmt)
            sheet2.write_number(c_row, 8, tot_grand, total_num_fmt)
            sheet2.write_number(c_row, 9, tot_dep, total_num_fmt)
            sheet2.write_number(c_row, 10, tot_rem, total_num_fmt)
            sheet2.write_number(c_row, 11, tot_plg, total_num_fmt)
            sheet2.write(c_row, 12, "", total_text_fmt)
            sheet2.write_number(c_row, 13, tot_dep_cash, total_num_fmt)
            sheet2.write_number(c_row, 14, tot_dep_visa, total_num_fmt)

        # --- Sheet 3: Pledge (Rahen) Detail ---
        if "pos.advance.order.pledge" in self.env:
            sheet3 = workbook.add_worksheet(_("Pledge (Rahen) Detail"))
            sheet3.write(0, 0, _("POS Pledge (Rahen) Audit List - In / Out"), title_fmt)
            sheet3.write(1, 0, _("Period: %s to %s") % (str_start, str_end), sub_fmt)

            plg_headers = [
                _("Customer"),
                _("Order Reference"),
                _("Pledge Item"),
                _("Branch Name"),
                _("Status"),
                _("Pledge (Rahen) In Amount"),
                _("Pledge (Rahen) In Cash"),
                _("Pledge (Rahen) In Visa"),
                _("Received On (Date & Time)"),
                _("Pledge (Rahen) Out Amount"),
                _("Pledge (Rahen) Out Cash"),
                _("Pledge (Rahen) Out Visa"),
                _("Returned On (Date & Time)"),
            ]

            sheet3.set_column(0, 0, 24)
            sheet3.set_column(1, 1, 22)
            sheet3.set_column(2, 2, 28)
            sheet3.set_column(3, 3, 24)
            sheet3.set_column(4, 4, 14)
            sheet3.set_column(5, 7, 16)
            sheet3.set_column(8, 8, 22)
            sheet3.set_column(9, 11, 16)
            sheet3.set_column(12, 12, 22)

            start_row_plg = 3
            for col_idx, h in enumerate(plg_headers):
                sheet3.write(start_row_plg, col_idx, h, header_fmt)

            pledge_dt_start, pledge_dt_end = service._parse_datetime_bounds(str_start, str_end)
            report_config_ids = set(service._get_report_configs(config_ids).ids)
            movements = service._get_pledge_movements(pledge_dt_start, pledge_dt_end, report_config_ids)
            movements.sort(key=lambda m: m["date"], reverse=True)

            p_row = start_row_plg + 1
            tot_rin = 0.0
            tot_rout = 0.0
            tot_rin_cash = tot_rin_visa = 0.0
            tot_rout_cash = tot_rout_visa = 0.0

            for move in movements:
                p = move["pledge"]
                is_in = move["type"] == "in"
                branch_name = move["config"].name or ""
                cust_name = p.partner_id.name if p.partner_id else ""
                order_ref = p.pos_order_id.name if p.pos_order_id else (p.order_id.name if p.order_id else "")
                prod_name = p.product_id.display_name if p.product_id else ""
                status_label = dict(p._fields["state"].selection).get(p.state, p.state)
                move_dt_str = fields.Datetime.to_string(move["date"])

                in_amt, in_cash, in_visa = (move["amount"], move["cash"], move["visa"]) if is_in else (0.0, 0.0, 0.0)
                out_amt, out_cash, out_visa = (0.0, 0.0, 0.0) if is_in else (move["amount"], move["cash"], move["visa"])
                rec_dt_str = move_dt_str if is_in else ""
                ret_dt_str = "" if is_in else move_dt_str

                sheet3.write(p_row, 0, cust_name, text_fmt)
                sheet3.write(p_row, 1, order_ref, text_fmt)
                sheet3.write(p_row, 2, prod_name, text_fmt)
                sheet3.write(p_row, 3, branch_name, text_fmt)
                sheet3.write(p_row, 4, status_label, center_fmt)
                sheet3.write_number(p_row, 5, in_amt, num_fmt)
                sheet3.write_number(p_row, 6, in_cash, num_fmt)
                sheet3.write_number(p_row, 7, in_visa, num_fmt)
                sheet3.write(p_row, 8, rec_dt_str, center_fmt)
                sheet3.write_number(p_row, 9, out_amt, num_fmt)
                sheet3.write_number(p_row, 10, out_cash, num_fmt)
                sheet3.write_number(p_row, 11, out_visa, num_fmt)
                sheet3.write(p_row, 12, ret_dt_str, center_fmt)

                tot_rin += in_amt
                tot_rout += out_amt
                tot_rin_cash += in_cash
                tot_rin_visa += in_visa
                tot_rout_cash += out_cash
                tot_rout_visa += out_visa
                p_row += 1

            # Total Row Sheet 3
            sheet3.write(p_row, 0, _("TOTALS"), total_text_fmt)
            for col in range(1, 5):
                sheet3.write(p_row, col, "", total_text_fmt)
            sheet3.write_number(p_row, 5, tot_rin, total_num_fmt)
            sheet3.write_number(p_row, 6, tot_rin_cash, total_num_fmt)
            sheet3.write_number(p_row, 7, tot_rin_visa, total_num_fmt)
            sheet3.write(p_row, 8, "", total_text_fmt)
            sheet3.write_number(p_row, 9, tot_rout, total_num_fmt)
            sheet3.write_number(p_row, 10, tot_rout_cash, total_num_fmt)
            sheet3.write_number(p_row, 11, tot_rout_visa, total_num_fmt)
            sheet3.write(p_row, 12, "", total_text_fmt)

            p_row += 1
            sheet3.write(p_row, 0, _("NET (In - Out)"), total_text_fmt)
            for col in range(1, 5):
                sheet3.write(p_row, col, "", total_text_fmt)
            sheet3.write_number(p_row, 5, tot_rin - tot_rout, total_num_fmt)
            sheet3.write_number(p_row, 6, tot_rin_cash - tot_rout_cash, total_num_fmt)
            sheet3.write_number(p_row, 7, tot_rin_visa - tot_rout_visa, total_num_fmt)
            for col in range(8, 13):
                sheet3.write(p_row, col, "", total_text_fmt)

        # --- Sheet 4: Cash Movements Detail (Cash In & Cash Out) ---
        sheet4 = workbook.add_worksheet(_("Cash Movements Detail"))
        sheet4.write(0, 0, _("POS Cash In & Cash Out Audit List"), title_fmt)
        sheet4.write(1, 0, _("Period: %s to %s") % (str_start, str_end), sub_fmt)

        cash_headers = [
            _("Branch Name"),
            _("Move Type"),
            _("Reference / Description"),
            _("Exact Move Date & Time"),
            _("Amount"),
            _("Cashier / User"),
            _("Session Reference"),
        ]

        sheet4.set_column(0, 0, 24)
        sheet4.set_column(1, 1, 16)
        sheet4.set_column(2, 2, 32)
        sheet4.set_column(3, 3, 22)
        sheet4.set_column(4, 4, 18)
        sheet4.set_column(5, 6, 24)

        start_row_cash = 3
        for col_idx, h in enumerate(cash_headers):
            sheet4.write(start_row_cash, col_idx, h, header_fmt)

        st_lines = self.env["account.bank.statement.line"].sudo().search([
            ("date", ">=", dt_start.date()),
            ("date", "<=", dt_end.date()),
        ], order="id desc")

        m_row = start_row_cash + 1
        tot_cin = 0.0
        tot_cout = 0.0

        for st in st_lines:
            cfg = st.pos_session_id.config_id if st.pos_session_id else False
            if target_config_ids and cfg and (cfg.id not in target_config_ids):
                continue

            branch_name = cfg.name if cfg else ""
            amt = st.amount or 0.0
            move_type = _("Cash In") if amt > 0 else _("Cash Out")

            st_dt = st.create_date or (datetime.combine(st.date, time.min) if st.date else self.date_from)
            st_dt_str = fields.Datetime.to_string(st_dt) if st_dt else ""

            user_name = st.create_uid.name if st.create_uid else ""
            session_ref = st.pos_session_id.name if st.pos_session_id else ""
            ref_desc = st.payment_ref or st.ref or st.name or ""

            sheet4.write(m_row, 0, branch_name, text_fmt)
            sheet4.write(m_row, 1, move_type, center_fmt)
            sheet4.write(m_row, 2, ref_desc, text_fmt)
            sheet4.write(m_row, 3, st_dt_str, center_fmt)
            sheet4.write_number(m_row, 4, abs(amt), num_fmt)
            sheet4.write(m_row, 5, user_name, text_fmt)
            sheet4.write(m_row, 6, session_ref, text_fmt)

            if amt > 0:
                tot_cin += amt
            else:
                tot_cout += abs(amt)
            m_row += 1

        # Total Row Sheet 4
        sheet4.write(m_row, 0, _("TOTALS"), total_text_fmt)
        sheet4.write(m_row, 1, _("Net: %s") % fields.Float.round(tot_cin - tot_cout, precision_digits=3), total_text_fmt)
        for col in range(2, 4):
            sheet4.write(m_row, col, "", total_text_fmt)
        sheet4.write_number(m_row, 4, tot_cin - tot_cout, total_num_fmt)
        sheet4.write(m_row, 5, "", total_text_fmt)
        sheet4.write(m_row, 6, "", total_text_fmt)

        workbook.close()
        return output.getvalue()
