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
        dt_start = self._to_datetime(self.date_from) or datetime.combine(fields.Date.context_today(self), time.min)
        dt_end = self._to_datetime(self.date_to) or datetime.combine(fields.Date.context_today(self), time.max)
        str_start = fields.Datetime.to_string(dt_start)
        str_end = fields.Datetime.to_string(dt_end)

        # Clear previous transient report records
        self.env["pos.unified.report"].sudo().search([]).unlink()

        config_domain = [("active", "=", True)]
        if self.config_ids:
            config_domain.append(("id", "in", self.config_ids.ids))
        configs = self.env["pos.config"].sudo().search(config_domain)
        active_config_ids = set(configs.ids)

        vals_list = []

        # POS Payments
        payments = self.env["pos.payment"].sudo().search([
            ("session_id.config_id", "in", list(active_config_ids)),
            ("payment_date", ">=", str_start),
            ("payment_date", "<=", str_end),
        ])
        for pay in payments:
            amt = pay.amount or 0.0
            pm = pay.payment_method_id
            daily_type = getattr(pm, "daily_ops_report_type", "")
            pm_type = getattr(pm, "type", "")
            pm_name = (pm.name or "").lower()

            is_emp = "ذمم" in pm_name or "موظف" in pm_name or "employee" in pm_name or "ذمة" in pm_name or "ذمه" in pm_name or daily_type == "employee_debt"
            is_hosp = daily_type == "hospitality" or "hospitality" in pm_name or "ضيافة" in pm_name

            if is_emp:
                is_cash = False
            key = (pay.pos_order_id.id, pay.payment_method_id.id)
            if key not in grouped_payments:
                pm = pay.payment_method_id
                pm_name = (pm.name or "").lower()
                daily_type = getattr(pm, "daily_ops_report_type", "")
                pm_type = getattr(pm, "type", "")
                is_emp = "ذمم" in pm_name or "موظف" in pm_name or "employee" in pm_name or "ذمة" in pm_name or "ذمه" in pm_name or daily_type == "employee_debt"
                is_hosp = daily_type == "hospitality" or "hospitality" in pm_name or "ضيافة" in pm_name
                is_cash = False
                is_visa = False
                if not is_emp and not is_hosp:
                    is_cash = daily_type == "cash" or pm_type == "cash" or "cash" in pm_name or "نقد" in pm_name
                    is_visa = daily_type == "visa" or pm_type in ("bank", "pay_later") or "visa" in pm_name or "بطاقة" in pm_name or "card" in pm_name

                grouped_payments[key] = {
                    "net_amount": 0.0,
                    "po": pay.pos_order_id,
                    "pm": pm,
                    "cfg": pay.session_id.config_id,
                    "session_id": pay.session_id.id,
                    "date": pay.payment_date,
                    "is_emp": is_emp,
                    "is_cash": is_cash,
                    "is_visa": is_visa,
                }
            grouped_payments[key]["net_amount"] += (pay.amount or 0.0)

        for grp in grouped_payments.values():
            amt = grp["net_amount"]
            po = grp["po"]
            pm = grp["pm"]
            cfg = grp["cfg"]
            sess = self.env["pos.session"].sudo().browse(grp["session_id"]) if grp.get("session_id") else (po.session_id if po else False)
            end_bal = getattr(sess, "cash_register_balance_end_real", 0.0) or 0.0 if sess else 0.0

            if po and po.amount_total:
                ratio = amt / po.amount_total
            else:
                ratio = 1.0

            tax_amt = ((getattr(po, "amount_tax", 0.0) or 0.0) * ratio) if po else 0.0
            tot_amt = ((getattr(po, "amount_total", 0.0) or 0.0) * ratio) if po else amt
            untaxed_amt = getattr(po, "amount_untaxed", None) if po else None
            if untaxed_amt is None:
                untaxed_amt = tot_amt - tax_amt
            else:
                untaxed_amt = untaxed_amt * ratio

            order_disc = (sum(
                (l.price_unit or 0.0) * (l.qty or 0.0) * (l.discount / 100.0)
                for l in po.lines if l.discount
            ) * ratio) if po else 0.0

            vals_list.append({
                "name": po.name if po else _("POS Payment"),
                "date": grp["date"] or self.date_from,
                "config_id": cfg.id,
                "session_id": grp["session_id"],
                "payment_method_id": pm.id if pm else False,
                "pos_order_id": po.id if po else False,
                "report_type": "pos_sales",
                "amount": amt,
                "untaxed_amount": untaxed_amt,
                "tax_amount": tax_amt,
                "discount_amount": order_disc,
                "cash_amount": amt if grp["is_cash"] else 0.0,
                "visa_amount": amt if grp["is_visa"] else 0.0,
                "employee_debt_amount": amt if grp["is_emp"] else 0.0,
                "ending_balance": end_bal,
                "partner_id": po.partner_id.id if po else False,
                "company_id": cfg.company_id.id,
            })

        # Session Delivery Amounts
        sessions = self.env["pos.session"].sudo().search([
            ("config_id", "in", list(active_config_ids)),
            "|",
            "&", ("start_at", ">=", str_start), ("start_at", "<=", str_end),
            "&", ("create_date", ">=", str_start), ("create_date", "<=", str_end),
        ])
        for sess in sessions:
            del_amt = getattr(sess, "delivery_amount", 0.0) or 0.0
            if del_amt != 0.0:
                end_bal = getattr(sess, "cash_register_balance_end_real", 0.0) or 0.0
                vals_list.append({
                    "name": _("Session Delivery Amount: %s") % sess.name,
                    "date": sess.start_at or sess.create_date or self.date_from,
                    "config_id": sess.config_id.id,
                    "session_id": sess.id,
                    "report_type": "pos_sales",
                    "amount": del_amt,
                    "delivery_amount": del_amt,
                    "ending_balance": end_bal,
                    "company_id": sess.config_id.company_id.id,
                })

        # Statement Lines (Cash In / Out for Sessions Started on Start Date)
        start_day = dt_start.date()
        target_sessions = self.env["pos.session"].sudo().search([
            ("config_id", "in", list(active_config_ids)),
            "|",
            "&", ("start_at", ">=", fields.Datetime.to_string(datetime.combine(start_day, time.min))),
                 ("start_at", "<=", fields.Datetime.to_string(datetime.combine(start_day, time.max))),
            "&", ("create_date", ">=", fields.Datetime.to_string(datetime.combine(start_day, time.min))),
                 ("create_date", "<=", fields.Datetime.to_string(datetime.combine(start_day, time.max))),
        ])
        target_session_ids = set(target_sessions.ids)

        if target_session_ids:
            st_lines = self.env["account.bank.statement.line"].sudo().search([
                ("pos_session_id", "in", list(target_session_ids)),
            ])
            for st in st_lines:
                amt = st.amount or 0.0
                is_in = amt > 0
                st_dt = st.create_date or (datetime.combine(st.date, time.min) if st.date else self.date_from)
                vals_list.append({
                    "name": st.payment_ref or st.ref or _("Cash Move"),
                    "date": st_dt,
                    "config_id": st.pos_session_id.config_id.id,
                    "session_id": st.pos_session_id.id,
                    "report_type": "cash_in" if is_in else "cash_out",
                    "amount": abs(amt),
                    "cash_in_amount": amt if is_in else 0.0,
                    "cash_out_amount": abs(amt) if not is_in else 0.0,
                    "partner_id": st.partner_id.id if st.partner_id else False,
                    "company_id": st.pos_session_id.config_id.company_id.id,
                })

        # Pledges (Rahen In / Out)
        if "pos.advance.order.pledge" in self.env:
            pledge_recs = self.env["pos.advance.order.pledge"].sudo().search([])
            for pledge in pledge_recs:
                cfg_id = False
                if pledge.pos_order_id:
                    cfg_id = pledge.pos_order_id.config_id.id
                elif pledge.order_id and hasattr(pledge.order_id, "pos_config_id"):
                    cfg_id = pledge.order_id.pos_config_id.id
                elif pledge.order_id and hasattr(pledge.order_id, "from_pos_config_id"):
                    cfg_id = pledge.order_id.from_pos_config_id.id

                if not cfg_id or cfg_id not in active_config_ids:
                    continue

                amt = pledge.pledge_subtotal or (getattr(pledge, "pledge_qty", 1.0) * getattr(pledge, "pledge_amount_unit", 0.0)) or getattr(pledge, "pledge_amount", 0.0) or 0.0

                rec_dt = self._to_datetime(pledge.receive_date) or self._to_datetime(pledge.create_date)
                ret_dt = self._to_datetime(pledge.return_date) or (self._to_datetime(pledge.write_date) if pledge.state == "returned" else None)

                if rec_dt and dt_start <= rec_dt <= dt_end:
                    vals_list.append({
                        "name": pledge.display_name or _("Pledge Record"),
                        "date": rec_dt,
                        "config_id": cfg_id,
                        "report_type": "rahen_in",
                        "amount": amt,
                        "rahen_in_amount": amt,
                        "partner_id": pledge.partner_id.id if hasattr(pledge, "partner_id") else False,
                    })

                if pledge.state == "returned" and ret_dt and dt_start <= ret_dt <= dt_end:
                    vals_list.append({
                        "name": pledge.display_name or _("Pledge Return Record"),
                        "date": ret_dt,
                        "config_id": cfg_id,
                        "report_type": "rahen_out",
                        "amount": amt,
                        "rahen_out_amount": amt,
                        "partner_id": pledge.partner_id.id if hasattr(pledge, "partner_id") else False,
                    })

        # Advance Orders
        if "pos.advance.order" in self.env:
            adv_orders = self.env["pos.advance.order"].sudo().search([
                ("state", "not in", ("draft", "cancel")),
            ])
            for adv in adv_orders:
                cfg_id = adv.from_pos_config_id.id if adv.from_pos_config_id else (adv.pos_config_id.id if adv.pos_config_id else False)
                if not cfg_id or cfg_id not in active_config_ids:
                    continue

                c_dt = self._to_datetime(adv.create_date)
                if c_dt and dt_start <= c_dt <= dt_end:
                    amt = adv.advance_amount or 0.0
                    vals_list.append({
                        "name": adv.name or _("Advance Order"),
                        "date": c_dt,
                        "config_id": cfg_id,
                        "report_type": "advance_deposit",
                        "amount": amt,
                        "advance_amount": amt,
                        "partner_id": adv.partner_id.id if hasattr(adv, "partner_id") else False,
                    })

        if vals_list:
            self.env["pos.unified.report"].sudo().create(vals_list)

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

        headers = [
            _("Branch Name"),
            _("Total Sales (Gross)"),
            _("Orders / Min"),
            _("Sales Without Tax"),
            _("Tax Amount"),
            _("Total Discounts"),
            _("Cash Sales"),
            _("Visa Sales"),
            _("Debt Sales (مبيعات الذمم)"),
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
            _("Advance Deposits (Origin)"),
            _("Pending Pickups"),
            _("Delivery Amount"),
        ]

        sheet1.set_column(0, 0, 28)
        for col_idx in range(1, len(headers)):
            sheet1.set_column(col_idx, col_idx, 16)

        start_row = 3
        for col_idx, h in enumerate(headers):
            sheet1.write(start_row, col_idx, h, header_fmt)

        curr_row = start_row + 1
        for b in data["branches"]:
            sheet1.write(curr_row, 0, b["branch_name"], text_fmt)
            sheet1.write_number(curr_row, 1, b["sales"], num_fmt)
            sheet1.write_number(curr_row, 2, b.get("orders_per_min", 0.0), num_fmt)
            sheet1.write_number(curr_row, 3, b["untaxed_sales"], num_fmt)
            sheet1.write_number(curr_row, 4, b["tax_amount"], num_fmt)
            sheet1.write_number(curr_row, 5, b.get("discount_amount", 0.0), num_fmt)
            sheet1.write_number(curr_row, 6, b["cash"], num_fmt)
            sheet1.write_number(curr_row, 7, b["visa"], num_fmt)
            sheet1.write_number(curr_row, 8, b.get("employee_debt", 0.0), num_fmt)
            sheet1.write_number(curr_row, 9, b["hospitality"], num_fmt)
            sheet1.write_number(curr_row, 10, b["talabat"], num_fmt)
            sheet1.write_number(curr_row, 11, b["careem"], num_fmt)
            sheet1.write_number(curr_row, 12, b["mythings"], num_fmt)
            sheet1.write_number(curr_row, 13, b["kabseh"], num_fmt)
            sheet1.write_number(curr_row, 14, b["cash_in"], num_fmt)
            sheet1.write_number(curr_row, 15, b["cash_out"], num_fmt)
            sheet1.write_number(curr_row, 16, b["net_cash_moves"], num_fmt)
            sheet1.write_number(curr_row, 17, b["rahen_in"], num_fmt)
            sheet1.write_number(curr_row, 18, b["rahen_out"], num_fmt)
            sheet1.write_number(curr_row, 19, b["net_pledges"], num_fmt)
            sheet1.write_number(curr_row, 20, b["advance_deposits"], num_fmt)
            sheet1.write_number(curr_row, 21, b.get("advance_pending_count", 0), int_fmt)
            sheet1.write_number(curr_row, 22, b["delivery_amount"], num_fmt)
            curr_row += 1

        # Global Total Row Sheet 1
        gt = data["global_totals"]
        sheet1.write(curr_row, 0, _("TOTALS"), total_text_fmt)
        sheet1.write_number(curr_row, 1, gt["sales"], total_num_fmt)
        sheet1.write_number(curr_row, 2, gt.get("orders_per_min", 0.0), total_num_fmt)
        sheet1.write_number(curr_row, 3, gt["untaxed_sales"], total_num_fmt)
        sheet1.write_number(curr_row, 4, gt["tax_amount"], total_num_fmt)
        sheet1.write_number(curr_row, 5, gt.get("discount_amount", 0.0), total_num_fmt)
        sheet1.write_number(curr_row, 6, gt["cash"], total_num_fmt)
        sheet1.write_number(curr_row, 7, gt["visa"], total_num_fmt)
        sheet1.write_number(curr_row, 8, gt.get("employee_debt", 0.0), total_num_fmt)
        sheet1.write_number(curr_row, 9, gt["hospitality"], total_num_fmt)
        sheet1.write_number(curr_row, 10, gt["talabat"], total_num_fmt)
        sheet1.write_number(curr_row, 11, gt["careem"], total_num_fmt)
        sheet1.write_number(curr_row, 12, gt["mythings"], total_num_fmt)
        sheet1.write_number(curr_row, 13, gt["kabseh"], total_num_fmt)
        sheet1.write_number(curr_row, 14, gt["cash_in"], total_num_fmt)
        sheet1.write_number(curr_row, 15, gt["cash_out"], total_num_fmt)
        sheet1.write_number(curr_row, 16, gt["net_cash_moves"], total_num_fmt)
        sheet1.write_number(curr_row, 17, gt["rahen_in"], total_num_fmt)
        sheet1.write_number(curr_row, 18, gt["rahen_out"], total_num_fmt)
        sheet1.write_number(curr_row, 19, gt["net_pledges"], total_num_fmt)
        sheet1.write_number(curr_row, 20, gt["advance_deposits"], total_num_fmt)
        sheet1.write_number(curr_row, 21, gt.get("advance_pending_count", 0), total_int_fmt)
        sheet1.write_number(curr_row, 22, gt["delivery_amount"], total_num_fmt)

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
                _("Payment Method"),
                _("Status"),
                _("Total Amount"),
                _("Advance Deposit Paid"),
                _("Remaining Balance"),
                _("Pledge Amount"),
            ]

            sheet2.set_column(0, 0, 20)
            sheet2.set_column(1, 2, 22)
            sheet2.set_column(3, 4, 24)
            sheet2.set_column(5, 6, 24)
            sheet2.set_column(7, 8, 18)
            sheet2.set_column(9, 12, 18)

            start_row_adv = 3
            for col_idx, h in enumerate(adv_headers):
                sheet2.write(start_row_adv, col_idx, h, header_fmt)

            adv_recs = self.env["pos.advance.order"].sudo().search([("state", "not in", ("draft", "cancel"))], order="id desc")

            c_row = start_row_adv + 1
            tot_grand = 0.0
            tot_dep = 0.0
            tot_rem = 0.0
            tot_plg = 0.0

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

                pm_name = ""
                if hasattr(a, "pos_payment_method_id") and a.pos_payment_method_id:
                    pm_name = a.pos_payment_method_id.name
                elif hasattr(a, "payment_method") and a.payment_method:
                    pm_sel = dict(a._fields["payment_method"].selection) if hasattr(a._fields["payment_method"], "selection") else {}
                    pm_name = pm_sel.get(a.payment_method, str(a.payment_method).capitalize())

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
                sheet2.write(c_row, 7, pm_name, center_fmt)
                sheet2.write(c_row, 8, state_label, center_fmt)
                sheet2.write_number(c_row, 9, g_amt, num_fmt)
                sheet2.write_number(c_row, 10, d_amt, num_fmt)
                sheet2.write_number(c_row, 11, r_amt, num_fmt)
                sheet2.write_number(c_row, 12, p_amt, num_fmt)

                tot_grand += g_amt
                tot_dep += d_amt
                tot_rem += r_amt
                tot_plg += p_amt
                c_row += 1

            # Total Row Sheet 2
            sheet2.write(c_row, 0, _("TOTALS"), total_text_fmt)
            for col in range(1, 9):
                sheet2.write(c_row, col, "", total_text_fmt)
            sheet2.write_number(c_row, 9, tot_grand, total_num_fmt)
            sheet2.write_number(c_row, 10, tot_dep, total_num_fmt)
            sheet2.write_number(c_row, 11, tot_rem, total_num_fmt)
            sheet2.write_number(c_row, 12, tot_plg, total_num_fmt)

        # --- Sheet 3: Pledges Detail (Rahen In & Rahen Out) ---
        if "pos.advance.order.pledge" in self.env:
            sheet3 = workbook.add_worksheet(_("Pledges Detail (Rahen In & Out)"))
            sheet3.write(0, 0, _("POS Pledges Audit List (Rahen In / Out)"), title_fmt)
            sheet3.write(1, 0, _("Period: %s to %s") % (str_start, str_end), sub_fmt)

            plg_headers = [
                _("Customer"),
                _("Order Reference"),
                _("Pledge Item"),
                _("Branch Name"),
                _("Status"),
                _("Rahen In Amount"),
                _("Received On (Date & Time)"),
                _("Rahen Out Amount"),
                _("Returned On (Date & Time)"),
            ]

            sheet3.set_column(0, 0, 24)
            sheet3.set_column(1, 1, 22)
            sheet3.set_column(2, 2, 28)
            sheet3.set_column(3, 3, 24)
            sheet3.set_column(4, 4, 14)
            sheet3.set_column(5, 5, 18)
            sheet3.set_column(6, 6, 22)
            sheet3.set_column(7, 7, 18)
            sheet3.set_column(8, 8, 22)

            start_row_plg = 3
            for col_idx, h in enumerate(plg_headers):
                sheet3.write(start_row_plg, col_idx, h, header_fmt)

            pledge_recs = self.env["pos.advance.order.pledge"].sudo().search([], order="id desc")

            p_row = start_row_plg + 1
            tot_rin = 0.0
            tot_rout = 0.0

            for p in pledge_recs:
                cfg = False
                if p.pos_order_id:
                    cfg = p.pos_order_id.config_id
                elif p.order_id and hasattr(p.order_id, "pos_config_id"):
                    cfg = p.order_id.pos_config_id
                elif p.order_id and hasattr(p.order_id, "from_pos_config_id"):
                    cfg = p.order_id.from_pos_config_id

                if target_config_ids and cfg and (cfg.id not in target_config_ids):
                    continue

                branch_name = cfg.name if cfg else ""
                cust_name = p.partner_id.name if p.partner_id else ""
                order_ref = p.pos_order_id.name if p.pos_order_id else (p.order_id.name if p.order_id else "")
                prod_name = p.product_id.display_name if p.product_id else ""
                status_label = dict(p._fields["state"].selection).get(p.state, p.state)
                amt = p.pledge_subtotal or (getattr(p, "pledge_qty", 1.0) * getattr(p, "pledge_amount_unit", 0.0)) or 0.0

                rec_dt = self._to_datetime(p.receive_date) or self._to_datetime(p.create_date)
                ret_dt = self._to_datetime(p.return_date) or (self._to_datetime(p.write_date) if p.state == "returned" else None)

                in_amt = 0.0
                if rec_dt and (dt_start <= rec_dt <= dt_end):
                    in_amt = amt

                out_amt = 0.0
                if p.state == "returned" and ret_dt and (dt_start <= ret_dt <= dt_end):
                    out_amt = amt

                if in_amt == 0.0 and out_amt == 0.0:
                    continue

                rec_dt_str = fields.Datetime.to_string(rec_dt) if in_amt > 0 else ""
                ret_dt_str = fields.Datetime.to_string(ret_dt) if out_amt > 0 else ""

                sheet3.write(p_row, 0, cust_name, text_fmt)
                sheet3.write(p_row, 1, order_ref, text_fmt)
                sheet3.write(p_row, 2, prod_name, text_fmt)
                sheet3.write(p_row, 3, branch_name, text_fmt)
                sheet3.write(p_row, 4, status_label, center_fmt)
                sheet3.write_number(p_row, 5, in_amt, num_fmt)
                sheet3.write(p_row, 6, rec_dt_str, center_fmt)
                sheet3.write_number(p_row, 7, out_amt, num_fmt)
                sheet3.write(p_row, 8, ret_dt_str, center_fmt)

                tot_rin += in_amt
                tot_rout += out_amt
                p_row += 1

            # Total Row Sheet 3
            sheet3.write(p_row, 0, _("TOTALS"), total_text_fmt)
            for col in range(1, 5):
                sheet3.write(p_row, col, "", total_text_fmt)
            sheet3.write_number(p_row, 5, tot_rin, total_num_fmt)
            sheet3.write(p_row, 6, "", total_text_fmt)
            sheet3.write_number(p_row, 7, tot_rout, total_num_fmt)
            sheet3.write(p_row, 8, "", total_text_fmt)

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

        start_day = dt_start.date()
        target_sessions_sheet4 = self.env["pos.session"].sudo().search([
            "|",
            "&", ("start_at", ">=", fields.Datetime.to_string(datetime.combine(start_day, time.min))),
                 ("start_at", "<=", fields.Datetime.to_string(datetime.combine(start_day, time.max))),
            "&", ("create_date", ">=", fields.Datetime.to_string(datetime.combine(start_day, time.min))),
                 ("create_date", "<=", fields.Datetime.to_string(datetime.combine(start_day, time.max))),
        ])
        target_session_ids_sheet4 = set(target_sessions_sheet4.ids)
        st_lines = self.env["account.bank.statement.line"].sudo().search([
            ("pos_session_id", "in", list(target_session_ids_sheet4)),
        ], order="id desc") if target_session_ids_sheet4 else self.env["account.bank.statement.line"]

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
