import calendar
import io
from datetime import datetime, time

from odoo import _, fields, models, exceptions
from odoo.tools.misc import format_date


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    def action_export_payrun_excel(self):
        self.ensure_one()
        url = f"/anabtawi_payroll/payrun/xlsx?payrun_id={self.id}"
        
        ctx = self.env.context
        if ctx.get("active_model") == "hr.payslip" and ctx.get("active_ids"):
            selected_ids = ",".join(str(i) for i in ctx.get("active_ids"))
            url += f"&payslip_ids={selected_ids}"

        return {
            "name": "PayRun Audit",
            "type": "ir.actions.act_url",
            "url": url,
            "target": "self",
        }

    def _generate_payrun_xlsx(self, quick_audit=False, payslip_ids=None):
        self.ensure_one()
        import xlsxwriter  # pylint: disable=import-outside-toplevel

        workbook_buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(workbook_buffer, {"in_memory": True})

        # Styling Definitions
        title_fmt = workbook.add_format(
            {"bold": True, "font_size": 15, "font_color": "#1F497D"}
        )
        meta_label_fmt = workbook.add_format(
            {"bold": True, "bg_color": "#F2F4F8", "border": 1, "font_size": 10}
        )
        meta_val_fmt = workbook.add_format(
            {"border": 1, "font_size": 10, "align": "left"}
        )
        
        card_header_fmt = workbook.add_format(
            {"bold": True, "bg_color": "#D9E1F2", "border": 1, "align": "center", "font_size": 10}
        )
        card_val_fmt = workbook.add_format(
            {"bold": True, "border": 1, "align": "center", "font_size": 11, "num_format": "#,##0.00"}
        )

        header_fmt = workbook.add_format(
            {
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": "#1F497D",
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
                "font_size": 10,
            }
        )

        group_header_alw_fmt = workbook.add_format(
            {
                "bold": True,
                "font_color": "#375623",
                "bg_color": "#E2EFDA",
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "font_size": 11,
            }
        )

        group_header_ded_fmt = workbook.add_format(
            {
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": "#C00000",
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "font_size": 11,
            }
        )

        group_header_comp_fmt = workbook.add_format(
            {
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": "#203764",
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
                "font_size": 10,
            }
        )

        text_left_fmt = workbook.add_format({"border": 1, "align": "left", "font_size": 10})
        text_center_fmt = workbook.add_format({"border": 1, "align": "center", "font_size": 10})
        number_fmt = workbook.add_format({"border": 1, "align": "right", "num_format": "#,##0.00", "font_size": 10})
        int_fmt = workbook.add_format({"border": 1, "align": "right", "num_format": "#,##0", "font_size": 10})

        net_negative_fmt = workbook.add_format(
            {"border": 1, "align": "right", "num_format": "#,##0.00", "font_size": 10, "bg_color": "#FCE4D6", "font_color": "#C00000", "bold": True}
        )

        total_label_fmt = workbook.add_format(
            {"bold": True, "border": 1, "bg_color": "#E9ECEF", "align": "left", "font_size": 10}
        )
        total_num_fmt = workbook.add_format(
            {"bold": True, "border": 1, "bg_color": "#E9ECEF", "align": "right", "num_format": "#,##0.00", "font_size": 10}
        )
        total_int_fmt = workbook.add_format(
            {"bold": True, "border": 1, "bg_color": "#E9ECEF", "align": "right", "num_format": "#,##0", "font_size": 10}
        )

        audit_ok_fmt = workbook.add_format({"border": 1, "align": "center", "bg_color": "#E2EFDA", "font_color": "#375623", "bold": True})
        audit_warn_fmt = workbook.add_format({"border": 1, "align": "center", "bg_color": "#FFF2CC", "font_color": "#7F6000", "bold": True})
        audit_err_fmt = workbook.add_format({"border": 1, "align": "center", "bg_color": "#FCE4D6", "font_color": "#C00000", "bold": True})

        # Filter payslips to only include selected employee payslips if specified
        if payslip_ids:
            payslips = self.env["hr.payslip"].browse(payslip_ids)
        else:
            payslips = self.slip_ids

        # -------------------------------------------------------------
        # SHEET 1: PayRun Audit
        # -------------------------------------------------------------
        sheet1_name = "PayRun Audit"

        sheet1 = workbook.add_worksheet(sheet1_name)
        sheet1.set_landscape()

        # Write Metadata (Rows 0-5)
        sheet1.write(0, 0, f"Odoo Payroll Report - PayRun Audit ({self.name or _('Pay Run')})", title_fmt)

        meta_items = [
            (_("Pay Run ID / Name"), self.name or "N/A"),
            (_("Period From"), format_date(self.env, self.date_start) if self.date_start else "N/A"),
            (_("Period To"), format_date(self.env, self.date_end) if self.date_end else "N/A"),
            (_("Generated By"), self.env.user.name or "System"),
            (_("Generated On"), fields.Datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            (_("Source System"), "Odoo 19 Payroll"),
            (_("Template Version"), "v1.5 (Dynamic Allowances & Group Headers)"),
        ]

        row = 2
        for i, (label, val) in enumerate(meta_items):
            c_idx = (i % 2) * 3
            r_idx = row + (i // 2)
            sheet1.write(r_idx, c_idx, label, meta_label_fmt)
            sheet1.write(r_idx, c_idx + 1, val, meta_val_fmt)

        row = 7
        # Write KPI / Summary block directly from computed payslip wages
        total_gross_val = sum(payslips.mapped("gross_wage") if "gross_wage" in payslips._fields else [
            sum(p.line_ids.filtered(lambda l: l.code == "GROSS" or l.category_id.code in ("GROSS", "Gross")).mapped("total")) for p in payslips
        ])
        total_net_val = sum(payslips.mapped("net_wage") if "net_wage" in payslips._fields else [
            sum(p.line_ids.filtered(lambda l: l.code == "NET" or l.category_id.code in ("NET", "Net")).mapped("total")) for p in payslips
        ])
        
        # Calculate summary metrics directly from exact system rule codes
        all_lines = payslips.mapped("line_ids")
        tax_lines = all_lines.filtered(lambda l: l.code in ("INCOME_TAX", "TAX", "IT") or "ضريبة" in l.name)
        ssc_comp_lines = all_lines.filtered(lambda l: l.code in ("SSC", "SSCC", "SSC_COMP", "SOC_SEC_COMP") or ("ضمان" in l.name and "شركة" in l.name))
        ssc_emp_lines = all_lines.filtered(lambda l: l.code in ("SSE", "SSCE", "SSC_EMP", "SOC_SEC_EMP") or ("ضمان" in l.name and "موظف" in l.name))
        loan_lines = all_lines.filtered(lambda l: l.code in ("COMPANY", "COMLON", "adv_pay", "adve", "LOAN", "LOANS", "ADVANCE") or "سلفة" in l.name or "سلفيات" in l.name)
        
        total_tax = sum(tax_lines.mapped("total"))
        total_ssc = sum(ssc_comp_lines.mapped("total")) + sum(ssc_emp_lines.mapped("total"))
        emp_count = len(payslips)
        avg_net = (total_net_val / emp_count) if emp_count > 0 else 0.0

        sheet1.write(row, 0, _("Total Gross (JOD)"), card_header_fmt)
        sheet1.write(row, 1, _("Total Tax (JOD)"), card_header_fmt)
        sheet1.write(row, 2, _("Total SSC (JOD)"), card_header_fmt)
        sheet1.write(row, 3, _("Total Net (JOD)"), card_header_fmt)
        sheet1.write(row, 4, _("Avg Net / Emp (JOD)"), card_header_fmt)

        sheet1.write_number(row + 1, 0, total_gross_val, card_val_fmt)
        sheet1.write_number(row + 1, 1, total_tax, card_val_fmt)
        sheet1.write_number(row + 1, 2, total_ssc, card_val_fmt)
        sheet1.write_number(row + 1, 3, total_net_val, card_val_fmt)
        sheet1.write_number(row + 1, 4, avg_net, card_val_fmt)

        row += 3

        # -------------------------------------------------------------
        # Dynamic Columns Discovery & Grouping (Allowances & Deductions)
        # -------------------------------------------------------------
        info_cols = [
            (_("Employee ID"), 14),
            (_("Employee Name"), 28),
            (_("Department"), 22),
            (_("Job Title / Position"), 22),
            (_("Internal Code"), 16),
            (_("SSC Subject Wage"), 18),
            (_("Period From"), 14),
            (_("Period To"), 14),
        ]

        key_cols = [
            (_("Net Salary"), 18),
            (_("Attendance Days"), 16),
            (_("Out of Contract Days"), 20),
        ]

        fixed_alw_cols = [
            (_("Basic Salary"), 16),
            (_("Actual Salary"), 16),
            (_("Remaining Leaves Comp"), 20),
            (_("Gross Attendance / OT"), 20),
        ]

        fixed_ded_cols = [
            (_("Income Tax"), 16),
            (_("SSC Employee Contrib"), 20),
        ]

        fixed_comp_cols = [
            (_("SSC Company Contrib"), 20),
        ]

        summary_cols = [
            (_("Worked Hours"), 15),
            (_("Overtime Hours"), 15),
            (_("Note / Description"), 30),
        ]

        # --- 1. Discover Dynamic Allowance Rules ---
        all_alw_lines = payslips.mapped("line_ids").filtered(
            lambda l: (
                (l.category_id and l.category_id.code in ("ALW", "Allowance", "ALLOWANCE"))
                or (l.category_id and "allowance" in (l.category_id.name or "").lower())
            )
            and not (l.code in ("BASIC", "SALARY") or (l.category_id and l.category_id.code in ("BASIC", "Basic")))
            and not (l.code in ("FULL_WAGE", "ACTUAL_SALARY", "ACTUAL") or "actual salary" in (l.name or "").lower() or "الراتب الفعلي" in (l.name or ""))
            and not (l.code in ("vacation_leave", "remain_lev", "REM_LEAVE", "LEAVE_COMP", "ANNUAL_LEAVE"))
            and not (l.code in ("OT_NET", "ETH_NET", "RD-S", "OVERTIME", "GROSS_ATT", "OT_COMP", "EXTRA_HOURS"))
        )

        alw_map = {}
        for line in all_alw_lines:
            rule = line.salary_rule_id
            rule_key = rule.id if rule else line.code
            rule_name = (rule.name if rule and rule.name else (line.name or line.code or _("Allowance"))).strip()
            if "copy" in rule_name.lower() or "copy" in (line.code or "").lower():
                continue
            norm_key = (rule.name.lower().strip() if rule and rule.name else (line.code or rule_name).lower().strip())
            if "copy" in norm_key:
                continue
            if norm_key not in alw_map:
                alw_map[norm_key] = {"name": rule_name, "rule_keys": set(), "input_type_ids": set()}
            alw_map[norm_key]["rule_keys"].add(rule_key)

        # --- 2. Discover Dynamic Deduction Rules ---
        all_ded_lines = payslips.mapped("line_ids").filtered(
            lambda l: (
                (l.category_id and l.category_id.code in ("DED", "Deduction", "DEDUCTION", "Social Security Deduction"))
                or (l.category_id and "deduction" in (l.category_id.name or "").lower())
            )
            and not (l.code in ("INCOME_TAX", "TAX", "IT") or "ضريبة" in (l.name or ""))
            and not (l.code in ("SSE", "SSCE", "SSC_EMP", "SOC_SEC_EMP") or ("ضمان" in (l.name or "") and "موظف" in (l.name or "")))
            and not (l.code in ("SSC", "SSCC", "SSC_COMP", "SOC_SEC_COMP") or ("ضمان" in (l.name or "") and "شركة" in (l.name or "")))
        )

        def _normalize_key(text_or_rule_name):
            if not text_or_rule_name:
                return ""
            s = text_or_rule_name.lower().strip()
            return s.replace("advance two", "advance 2").replace("advances two", "advances 2")

        # Helper to check if a name or code represents Advance #2
        def _is_adv_2(text_name, code_str):
            t = (text_name or "").lower()
            c = (code_str or "").lower()
            return c in ("sala2", "saladv2") or any(x in t for x in ("advance 2", "advances 2", "advance two", "advances two"))

        ded_map = {}
        for line in all_ded_lines:
            rule = line.salary_rule_id
            rule_key = rule.id if rule else line.code
            raw_rule_name = (rule.name if rule and rule.name else (line.name or line.code or _("Deduction"))).strip()
            if "copy" in raw_rule_name.lower() or "copy" in (line.code or "").lower():
                continue
            rule_name = raw_rule_name.replace("Advances Two", "Advances 2").replace("Advance Two", "Advance 2")
            norm_key = _normalize_key(rule.name if rule and rule.name else (line.code or rule_name))
            if "copy" in norm_key:
                continue
            if norm_key not in ded_map:
                ded_map[norm_key] = {"name": rule_name, "rule_keys": set(), "input_type_ids": set()}
            ded_map[norm_key]["rule_keys"].add(rule_key)

        # --- 3. Process Salary Inputs (Classify & Deduplicate into Allowance vs Deduction) ---
        input_types = payslips.mapped("input_line_ids.input_type_id").sorted(key=lambda t: t.name or "")
        ded_rule_names = set(ded_map.keys())

        if input_types:
            for itype in input_types:
                raw_t_name = (itype.name or _("Salary Input")).strip()
                if "copy" in raw_t_name.lower() or "copy" in (getattr(itype, "code", "") or "").lower():
                    continue
                t_name = raw_t_name.replace("Advances Two", "Advances 2").replace("Advance Two", "Advance 2")
                t_norm = _normalize_key(t_name)
                t_code = (getattr(itype, "code", "") or "").lower()
                itype_is_adv2 = _is_adv_2(t_norm, t_code)

                is_deduction_input = (
                    "deduction" in t_norm
                    or "ded" in t_code
                    or "adv" in t_code
                    or "advance" in t_norm
                    or "advances" in t_norm
                    or "saladv" in t_code
                    or "sala2" in t_code
                    or itype_is_adv2
                    or any(
                        t_norm == d_name
                        or (t_code and t_code == d_name)
                        for d_name in ded_rule_names
                    )
                )

                if is_deduction_input:
                    matched_key = None
                    for k in ded_map:
                        k_is_adv2 = _is_adv_2(k, k)
                        if k_is_adv2 == itype_is_adv2:
                            if k == t_norm or (t_code and t_code == k):
                                matched_key = k
                                break
                    if matched_key:
                        ded_map[matched_key]["input_type_ids"].add(itype.id)
                    else:
                        ded_map[t_norm] = {"name": t_name, "rule_keys": set(), "input_type_ids": {itype.id}}
                else:
                    matched_key = None
                    clean_input_norm = t_norm.replace("input:", "").strip()
                    for k in alw_map:
                        k_is_adv2 = _is_adv_2(k, k)
                        if k_is_adv2 == itype_is_adv2:
                            if k == clean_input_norm or (t_code and t_code == k):
                                matched_key = k
                                break
                    if not matched_key and "car depreciation" in clean_input_norm:
                        matched_key = next((k for k in alw_map if "car depreciation" in k), None)
                        if not matched_key:
                            continue
                    if matched_key:
                        alw_map[matched_key]["input_type_ids"].add(itype.id)
                    else:
                        disp_name = f"Input: {t_name}" if not t_name.lower().startswith("input") else t_name
                        alw_map[clean_input_norm] = {"name": disp_name, "rule_keys": set(), "input_type_ids": {itype.id}}

        # Order dynamic columns deterministically by display name and include ONLY non-zero total columns
        dynamic_alw_cols = []
        for norm_k in sorted(alw_map.keys(), key=lambda k: alw_map[k]["name"]):
            col_info = alw_map[norm_k]
            c_name = col_info["name"]
            if "copy" in c_name.lower():
                continue
            rule_keys = col_info["rule_keys"]
            input_type_ids = col_info["input_type_ids"]

            # Calculate total across all selected payslips prioritizing computed rule lines over input lines
            col_total = 0.0
            for payslip in payslips:
                lines = payslip.line_ids
                val = 0.0
                if rule_keys:
                    r_lines = lines.filtered(lambda l: (l.salary_rule_id and l.salary_rule_id.id in rule_keys) or l.code in rule_keys)
                    if r_lines:
                        val = sum(r_lines.mapped("total"))
                if abs(val) < 0.0001 and input_type_ids:
                    in_lines = payslip.input_line_ids.filtered(lambda l: l.input_type_id and l.input_type_id.id in input_type_ids)
                    if in_lines:
                        in_val = sum((l.amount if l.amount != 0.0 else l.quantity) or 0.0 for l in in_lines)
                        if abs(in_val) > 0.0001:
                            val = in_val
                col_total += val

            if abs(col_total) > 0.0001:
                dynamic_alw_cols.append((c_name, max(18, len(c_name) + 4), rule_keys, input_type_ids))

        dynamic_ded_cols = []
        for norm_k in sorted(ded_map.keys(), key=lambda k: ded_map[k]["name"]):
            col_info = ded_map[norm_k]
            c_name = col_info["name"]
            if "copy" in c_name.lower():
                continue

            c_name_lower = c_name.lower().replace(":", "").replace("_", " ").strip()
            if c_name_lower in ("deduction", "deductions", "خصم", "استقطاع"):
                continue

            rule_keys = col_info["rule_keys"]
            input_type_ids = col_info["input_type_ids"]

            # Calculate total across all selected payslips prioritizing computed rule lines over input lines
            col_total = 0.0
            for payslip in payslips:
                lines = payslip.line_ids
                val = 0.0
                if rule_keys:
                    r_lines = lines.filtered(lambda l: (l.salary_rule_id and l.salary_rule_id.id in rule_keys) or l.code in rule_keys)
                    if r_lines:
                        val = sum(r_lines.mapped("total"))
                if abs(val) < 0.0001 and input_type_ids:
                    in_lines = payslip.input_line_ids.filtered(lambda l: l.input_type_id and l.input_type_id.id in input_type_ids)
                    if in_lines:
                        in_val = sum((l.amount if l.amount != 0.0 else l.quantity) or 0.0 for l in in_lines)
                        if abs(in_val) > 0.0001:
                            val = in_val
                col_total += val

            if abs(col_total) > 0.0001:
                dynamic_ded_cols.append((c_name, max(18, len(c_name) + 4), rule_keys, input_type_ids))

        # --- 4. Column Definitions (group, header, width, kind) ---
        # kind: "text" = always shown, "num" = hidden automatically when the whole column is zero
        columns = []
        for name, width in info_cols:
            columns.append({"group": "info", "name": name, "width": width, "kind": "text"})
        columns[5]["kind"] = "num"  # SSC Subject Wage (hidden if all zero, not totaled)
        columns[5]["no_total"] = True

        columns.append({"group": "key", "name": _("Net Salary"), "width": 18, "kind": "num", "net": True})
        columns.append({"group": "key", "name": _("Attendance Days"), "width": 16, "kind": "num"})
        columns.append({"group": "key", "name": _("Out of Contract Days"), "width": 20, "kind": "num"})

        for name, width in fixed_alw_cols:
            columns.append({"group": "alw", "name": name, "width": width, "kind": "num"})
        for c_name, width, _rk, _it in dynamic_alw_cols:
            columns.append({"group": "alw", "name": c_name, "width": width, "kind": "num"})
        columns.append({"group": "alw", "name": _("Gross Salary (before tax)"), "width": 22, "kind": "num"})

        for name, width in fixed_ded_cols:
            columns.append({"group": "ded", "name": name, "width": width, "kind": "num"})
        for c_name, width, _rk, _it in dynamic_ded_cols:
            columns.append({"group": "ded", "name": c_name, "width": width, "kind": "num"})

        for name, width in fixed_comp_cols:
            columns.append({"group": "comp", "name": name, "width": width, "kind": "num"})

        columns.append({"group": "sum", "name": _("Worked Hours"), "width": 15, "kind": "num"})
        columns.append({"group": "sum", "name": _("Overtime Hours"), "width": 15, "kind": "num"})
        columns.append({"group": "sum", "name": _("Note / Description"), "width": 30, "kind": "text"})

        def _rule_or_input_value(payslip, lines, rule_keys, input_type_ids):
            val = 0.0
            if rule_keys:
                r_lines = lines.filtered(lambda l: (l.salary_rule_id and l.salary_rule_id.id in rule_keys) or l.code in rule_keys)
                if r_lines:
                    val = sum(r_lines.mapped("total"))
            if abs(val) < 0.0001 and input_type_ids:
                in_lines = payslip.input_line_ids.filtered(lambda l: l.input_type_id and l.input_type_id.id in input_type_ids)
                if in_lines:
                    in_val = sum((l.amount if l.amount != 0.0 else l.quantity) or 0.0 for l in in_lines)
                    if abs(in_val) > 0.0001:
                        val = in_val
            return val

        # --- 5. Collect Row Values (one list per payslip, same order as `columns`) ---
        rows = []
        audit_entries = []

        if not payslips:
            audit_entries.append({
                "emp_id": "N/A",
                "emp_name": "N/A",
                "dept": "N/A",
                "status": "WARNING",
                "remarks": _("No employees included in this selection."),
            })

        for payslip in payslips:
            emp = payslip.employee_id
            issues = []

            emp_id_val = (
                getattr(emp, "employee_number", False)
                or getattr(emp, "registration_number", False)
                or getattr(emp, "barcode", False)
                or (str(emp.id) if emp else "N/A")
            )
            if not emp:
                issues.append(_("Missing Employee record"))
            elif not getattr(emp, "employee_number", False):
                issues.append(_("Missing Employee Number"))

            emp_name_val = (emp.legal_name or emp.name) if emp else "N/A"
            dept_val = emp.department_id.name if emp and emp.department_id else "N/A"
            if emp and not emp.department_id:
                issues.append(_("Missing Department"))

            job_val = emp.job_id.name if emp and emp.job_id else "N/A"
            code_val = emp_id_val

            period_from_val = format_date(self.env, payslip.date_from or self.date_start)
            period_to_val = format_date(self.env, payslip.date_to or self.date_end)

            lines = payslip.line_ids

            # Base Allowances
            basic_sal = sum(lines.filtered(lambda l: l.code in ("BASIC", "SALARY") or (l.category_id and l.category_id.code in ("BASIC", "Basic")) or (l.category_id and l.category_id.name in ("BASIC", "Basic", "Basic Salary"))).mapped("total"))
            actual_sal = sum(lines.filtered(lambda l: l.code in ("FULL_WAGE", "ACTUAL_SALARY", "ACTUAL") or "actual salary" in (l.name or "").lower() or "الراتب الفعلي" in (l.name or "")).mapped("total"))
            rem_leave = sum(lines.filtered(lambda l: l.code in ("vacation_leave", "remain_lev", "REM_LEAVE", "LEAVE_COMP", "ANNUAL_LEAVE")).mapped("total"))
            gross_att_ot = sum(lines.filtered(lambda l: l.code in ("OT_NET", "ETH_NET", "RD-S", "OVERTIME", "GROSS_ATT", "OT_COMP", "EXTRA_HOURS")).mapped("total"))

            dyn_alw_vals = [_rule_or_input_value(payslip, lines, rk, it) for _n, _w, rk, it in dynamic_alw_cols]

            # Gross Salary (Actual Salary + Allowances)
            gross_sal = actual_sal + rem_leave + gross_att_ot + sum(dyn_alw_vals)

            # Fixed Deductions
            tax_val = sum(lines.filtered(lambda l: l.code in ("INCOME_TAX", "TAX", "IT") or "ضريبة" in (l.name or "")).mapped("total"))
            ssce_val = sum(lines.filtered(lambda l: l.code in ("SSE", "SSCE", "SSC_EMP", "SOC_SEC_EMP") or ("ضمان" in (l.name or "") and "موظف" in (l.name or ""))).mapped("total"))
            sscc_val = sum(lines.filtered(lambda l: l.code in ("SSC", "SSCC", "SSC_COMP", "SOC_SEC_COMP") or ("ضمان" in (l.name or "") and "شركة" in (l.name or ""))).mapped("total"))

            dyn_ded_vals = [_rule_or_input_value(payslip, lines, rk, it) for _n, _w, rk, it in dynamic_ded_cols]

            # Net Salary
            net_sal = payslip.net_wage if hasattr(payslip, "net_wage") and payslip.net_wage else sum(lines.filtered(lambda l: l.code == "NET" or (l.category_id and l.category_id.code in ("NET", "Net"))).mapped("total"))
            if net_sal < 0:
                issues.append(_("Negative Net Salary (%.2f JOD)") % net_sal)

            worked_days = payslip.worked_days_line_ids

            # Attendance Days are taken from the payslip itself, not recalculated:
            #   Attendance Days = Actual Salary / (Wage / calendar days in the month)
            # This always matches the Actual Salary salary rule on the payslip.
            ref_date = payslip.date_to or self.date_end
            days_in_month = calendar.monthrange(ref_date.year, ref_date.month)[1] if ref_date else 30
            wage_val = (emp.wage if emp else 0.0) or basic_sal or 0.0
            daily_wage = (wage_val / float(days_in_month)) if wage_val and days_in_month else 0.0
            att_days = round(actual_sal / daily_wage, 2) if daily_wage else 0.0

            # Out of Contract Days
            out_of_contract_days = 0.0
            for wd in worked_days:
                wd_code = (wd.work_entry_type_id.code or wd.code or '').strip().upper()
                wd_text = f"{(wd.name or '').lower()} {(wd.work_entry_type_id.name or '').lower()}"
                if (
                    wd_code in ('OUT', 'OUTCON', 'OUT_OF_CONTRACT')
                    or any(k in wd_text for k in ('out of contract', 'خارج العقد'))
                ):
                    out_of_contract_days += wd.number_of_days if wd.number_of_days else ((wd.number_of_hours or 0.0) / 8.0)

            worked_hrs = sum(worked_days.mapped("number_of_hours"))
            ot_hrs = sum(worked_days.filtered(lambda wd: "overtime" in (wd.code or "").lower() or "ot" in (wd.code or "").lower() or "extra" in (wd.code or "").lower()).mapped("number_of_hours"))

            # Notes
            input_notes = []
            for input_line in payslip.input_line_ids:
                note_txt = input_line.name or getattr(input_line, "note", False)
                if note_txt:
                    t_label = input_line.input_type_id.name or _("Input")
                    input_notes.append(f"[{t_label}: {note_txt}]")
            base_note = payslip.note or payslip.name or ""
            note_val = f"{base_note} {' '.join(input_notes)}".strip() if input_notes else base_note

            # SSC Subject Wage
            ssc_wage_val = 0.0
            if emp:
                for attr in ("x_studio_x_studio_ssc_wage", "x_studio_ssc_wage", "sb_ss_salary", "ssc_wage", "ss_wage", "social_security_wage", "ss_salary"):
                    val = getattr(emp, attr, 0.0)
                    if val:
                        ssc_wage_val = float(val)
                        break
            if not ssc_wage_val and hasattr(payslip, "version_id") and payslip.version_id:
                ssc_wage_val = payslip.version_id._get_contract_wage()

            row_vals = (
                [emp_id_val, emp_name_val, dept_val, job_val, code_val, ssc_wage_val, period_from_val, period_to_val]
                + [net_sal, att_days, out_of_contract_days]
                + [basic_sal, actual_sal, rem_leave, gross_att_ot] + dyn_alw_vals + [gross_sal]
                + [tax_val, ssce_val] + dyn_ded_vals
                + [sscc_val]
                + [worked_hrs, ot_hrs, note_val]
            )
            rows.append(row_vals)

            if not lines and payslip.state != "cancel":
                issues.append(_("Payslip lines not computed"))

            status = "ERROR" if any("Negative" in i or "not computed" in i for i in issues) else ("WARNING" if issues else "OK")
            remarks = ", ".join(issues) if issues else _("Computation verified cleanly")

            audit_entries.append({
                "emp_id": emp_id_val,
                "emp_name": emp_name_val,
                "dept": dept_val,
                "status": status,
                "remarks": remarks,
            })

        # --- 6. Drop numeric columns that are zero for every employee ---
        keep_idx = []
        col_totals = {}
        for i, col in enumerate(columns):
            if col["kind"] == "num":
                total = sum(float(r[i] or 0.0) for r in rows)
                col_totals[i] = total
                if rows and all(abs(float(r[i] or 0.0)) < 0.0001 for r in rows):
                    continue
            keep_idx.append(i)

        kept = [columns[i] for i in keep_idx]

        for out_c, col in enumerate(kept):
            sheet1.set_column(out_c, out_c, col["width"])

        # --- 7. Render 2-Tier Header Row ---
        row_super = row
        row_sub = row + 1

        group_ranges = {}
        for out_c, col in enumerate(kept):
            g = col["group"]
            if g not in group_ranges:
                group_ranges[g] = [out_c, out_c]
            group_ranges[g][1] = out_c

        for out_c, col in enumerate(kept):
            g = col["group"]
            if g in ("alw", "ded"):
                sheet1.write(row_sub, out_c, col["name"], header_fmt)
            else:
                fmt = group_header_comp_fmt if g == "comp" else header_fmt
                sheet1.merge_range(row_super, out_c, row_sub, out_c, col["name"], fmt)

        for g, label, fmt in (("alw", _("ALLOWANCE"), group_header_alw_fmt), ("ded", _("DEDUCTION"), group_header_ded_fmt)):
            if g in group_ranges:
                c1, c2 = group_ranges[g]
                if c2 > c1:
                    sheet1.merge_range(row_super, c1, row_super, c2, label, fmt)
                else:
                    sheet1.write(row_super, c1, label, fmt)

        # --- 8. Write Data Rows ---
        table_start_row = row_sub + 1
        data_row = table_start_row
        for r in rows:
            for out_c, src_i in enumerate(keep_idx):
                col = columns[src_i]
                val = r[src_i]
                if col["kind"] == "num":
                    style = net_negative_fmt if col.get("net") and (val or 0.0) < 0 else number_fmt
                    sheet1.write_number(data_row, out_c, float(val or 0.0), style)
                else:
                    style = text_center_fmt if src_i in (0, 4, 6, 7) else text_left_fmt
                    sheet1.write(data_row, out_c, val, style)
            data_row += 1

        # --- 9. Bottom Total Row (formula + pre-calculated value so it never shows 0) ---
        for out_c, src_i in enumerate(keep_idx):
            col = columns[src_i]
            if out_c == 0:
                sheet1.write(data_row, 0, _("Total"), total_label_fmt)
            elif col["kind"] == "num" and rows and not col.get("no_total"):
                col_letter = xlsxwriter.utility.xl_col_to_name(out_c)
                formula = f"=SUM({col_letter}{table_start_row + 1}:{col_letter}{data_row})"
                sheet1.write_formula(data_row, out_c, formula, total_num_fmt, round(col_totals[src_i], 3))
            else:
                sheet1.write(data_row, out_c, "", total_label_fmt)

        # -------------------------------------------------------------
        # SHEET 2: Audit
        # -------------------------------------------------------------
        sheet2 = workbook.add_worksheet("Audit")
        sheet2.set_column(0, 0, 14)
        sheet2.set_column(1, 1, 28)
        sheet2.set_column(2, 2, 22)
        sheet2.set_column(3, 3, 16)
        sheet2.set_column(4, 4, 45)

        sheet2.write(0, 0, _("Pay Run Audit Trail & Exception Log"), title_fmt)
        sheet2.write(1, 0, _("Pay Run: %s") % (self.name or ""), meta_val_fmt)

        audit_headers = [
            _("Employee ID"),
            _("Employee Name"),
            _("Department"),
            _("Audit Status"),
            _("Issue / Remarks"),
        ]
        for c_idx, h_text in enumerate(audit_headers):
            sheet2.write(3, c_idx, h_text, header_fmt)

        a_row = 4
        for entry in audit_entries:
            st = entry["status"]
            st_fmt = audit_ok_fmt if st == "OK" else (audit_warn_fmt if st == "WARNING" else audit_err_fmt)

            sheet2.write(a_row, 0, entry["emp_id"], text_center_fmt)
            sheet2.write(a_row, 1, entry["emp_name"], text_left_fmt)
            sheet2.write(a_row, 2, entry["dept"], text_left_fmt)
            sheet2.write(a_row, 3, st, st_fmt)
            sheet2.write(a_row, 4, entry["remarks"], text_left_fmt)
            a_row += 1

        sheet2.write(a_row, 0, _("Summary Total"), total_label_fmt)
        sheet2.write(a_row, 1, _("Total Audited Records: %d") % len(audit_entries), total_label_fmt)
        sheet2.write(a_row, 2, "", total_label_fmt)
        sheet2.write(a_row, 3, "", total_label_fmt)
        sheet2.write(a_row, 4, "", total_label_fmt)

        workbook.close()
        return workbook_buffer.getvalue()
