# -*- coding: utf-8 -*-
import base64
import io
import logging
from datetime import datetime, date, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    openpyxl = None


class HrPayrollReportWizard(models.TransientModel):
    _name = "hr.payroll.report.wizard"
    _description = "HR & Payroll Unified Excel Report Generator"

    date_from = fields.Date(string="Date From", required=True, default=lambda self: fields.Date.today().replace(day=1))
    date_to = fields.Date(string="Date To", required=True, default=lambda self: (fields.Date.today().replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1))
    payrun_id = fields.Many2one("hr.payslip.run", string="Payrun Batch", help="Filter by specific payroll batch")
    company_id = fields.Many2one("res.company", string="Company", default=lambda self: self.env.company, required=False)
    department_ids = fields.Many2many("hr.department", string="Departments")
    report_type = fields.Selection([
        ("all", "Complete HR & Payroll Package (All Sheets)"),
        ("labor_cost", "0. Employee Cost & Headcount Report (تقرير تكاليف القوى العاملة - 6 Sheets)"),
        ("payroll", "1. Monthly Payroll List"),
        ("overtime", "2. Monthly Overtime Analysis"),
        ("bank", "3. Bank Transfer File"),
        ("attendance", "4. Attendance Reconciliation"),
    ], string="Report Scope", default="all", required=True)

    company_source_account = fields.Char(string="Company Bank Account Number", default="0126046919500", help="Used in Bank Transfer file (BT/LBT)")

    excel_file = fields.Binary(string="Excel File", readonly=True)
    file_name = fields.Char(string="File Name")

    def _get_emp_code(self, emp):
        if not emp:
            return ""
        return str(
            getattr(emp, "registration_number", False)
            or getattr(emp, "employee_number", False)
            or getattr(emp, "barcode", False)
            or getattr(emp, "identification_id", False)
            or emp.id
        ).strip()

    def _get_emp_name_en(self, emp):
        if not emp:
            return ""
        return str(getattr(emp, "legal_name", False) or emp.name or "").strip()

    def action_export_xlsx(self):
        self.ensure_one()
        if not openpyxl:
            raise UserError(_("The openpyxl Python library is required for generating Excel reports."))

        slip_domain = [
            ("state", "not in", ["cancel"]),
        ]
        if self.company_id:
            slip_domain.append(("company_id", "=", self.company_id.id))
        else:
            slip_domain.append(("company_id", "in", self.env.user.company_ids.ids))

        if self.payrun_id:
            slip_domain.append(("payslip_run_id", "=", self.payrun_id.id))
        else:
            slip_domain.extend([
                ("date_from", "<=", self.date_to),
                ("date_to", ">=", self.date_from),
            ])

        all_target_dep_ids_set = set()
        if self.department_ids:
            all_target_dep_ids = self.env["hr.department"].sudo().search([("id", "child_of", self.department_ids.ids)]).ids
            all_target_dep_ids_set = set(all_target_dep_ids)
            slip_domain.extend([
                "|",
                ("employee_id.department_id", "in", all_target_dep_ids),
                ("department_id", "in", all_target_dep_ids),
            ])

        raw_payslips = self.env["hr.payslip"].search(slip_domain, order="department_id, employee_id")
        if all_target_dep_ids_set:
            payslips = raw_payslips.filtered(
                lambda s: (
                    ((s.employee_id and s.employee_id.department_id) or s.department_id).id in all_target_dep_ids_set
                ) if ((s.employee_id and s.employee_id.department_id) or s.department_id) else False
            )
        else:
            payslips = raw_payslips
        if not payslips:
            raise UserError(_("No payslip records found for the selected criteria."))

        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        font_header_title = Font(name="Arial", size=14, bold=True, color="1E3A8A")
        font_sub_title = Font(name="Arial", size=10, italic=True, color="475569")
        font_col_header = Font(name="Arial", size=9, bold=True, color="FFFFFF")
        font_sub_header = Font(name="Arial", size=9, bold=True, color="1E293B")
        font_data = Font(name="Arial", size=9)
        font_total = Font(name="Arial", size=9, bold=True, color="000000")

        fill_primary_header = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid")
        fill_alw_header = PatternFill(start_color="047857", end_color="047857", fill_type="solid")
        fill_ded_header = PatternFill(start_color="B91C1C", end_color="B91C1C", fill_type="solid")
        fill_sub_header = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
        fill_grand_total = PatternFill(start_color="FEF08A", end_color="FEF08A", fill_type="solid")

        thin_side = Side(border_style="thin", color="CBD5E1")
        border_all = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
        double_bottom = Border(left=thin_side, right=thin_side, top=thin_side, bottom=Side(border_style="double", color="000000"))

        align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        align_left = Alignment(horizontal="left", vertical="center")
        align_right = Alignment(horizontal="right", vertical="center")

        period_title = self.payrun_id.name if self.payrun_id else f"{self.date_from.strftime('%m/%Y')}"

        # -------------------------------------------------------------
        # SHEET 0: Labor Cost Report + 5 SBU Employee Cost Sheets (Matching Employee Cost.xlsx)
        # -------------------------------------------------------------
        if self.report_type in ["all", "labor_cost"]:
            dash_model = self.env["hr.payroll.dashboard"].sudo()
            dash_data = dash_model.get_dashboard_data(
                date_from=str(self.date_from),
                date_to=str(self.date_to),
                payrun_id=self.payrun_id.id if self.payrun_id else 0,
                company_id=self.company_id.id if self.company_id else 0,
                department_ids=self.department_ids.ids if self.department_ids else [],
            )
            lc_rows = dash_data.get("labor_cost_report", [])

            ws_lc = wb.create_sheet(title="Labor Cost Report")
            ws_lc.views.sheetView[0].showGridLines = True
            ws_lc.sheet_view.rightToLeft = True

            ws_lc.cell(row=1, column=1, value=f"تقرير تكاليف القوى العاملة  {period_title}").font = font_header_title

            lc_headers = [
                "الشركة",
                "عدد الموظفين بداية الشهر",
                "تعيينات جديدة",
                "إنهاء خدمات",
                "عدد الموظفين نهاية الشهر",
                "الرواتب الأساسية",
                "العلاوات والبدلات",
                "العمل الإضافي",
                "مساهمة الشركة تأمين صحي",
                "مساهمة الشركة ضمان اجتماعي",
                "مستحقات نهاية خدمة",
                "تسويات / مكافآت أخرى",
                "إجمالي تكلفة القوى العاملة",
                "متوسط تكلفة الموظف (بدون مستحقات نهاية الخدمة)",
                "نسبة العمل الإضافي",
            ]
            for c_i, h_text in enumerate(lc_headers, start=1):
                h_cell = ws_lc.cell(row=3, column=c_i, value=h_text)
                h_cell.font = font_col_header
                h_cell.fill = fill_primary_header
                h_cell.alignment = align_center
                h_cell.border = border_all

            r_idx = 4
            for sbu_r in lc_rows:
                row_vals = [
                    sbu_r.get("sbu_name_ar") or sbu_r.get("sbu_display_name"),
                    sbu_r.get("beginning_hc", 0),
                    sbu_r.get("new_hires", 0),
                    sbu_r.get("separations", 0),
                    f"=B{r_idx}+C{r_idx}-D{r_idx}",
                    round(sbu_r.get("basic_salary", 0.0), 3),
                    round(sbu_r.get("allowances", 0.0), 3),
                    round(sbu_r.get("overtime_amount", 0.0), 3),
                    round(sbu_r.get("health_ins_comp", 0.0), 3),
                    round(sbu_r.get("social_security_comp", 0.0), 3),
                    round(sbu_r.get("eos_amount", 0.0), 3),
                    round(sbu_r.get("other_adjustments", 0.0), 3),
                    f"=SUM(F{r_idx}:L{r_idx})",
                    f"=IF(E{r_idx}=0,0,(M{r_idx}-K{r_idx})/E{r_idx})",
                    f"=IF(M{r_idx}=0,0,H{r_idx}/M{r_idx})",
                ]
                for c_i, val in enumerate(row_vals, start=1):
                    c = ws_lc.cell(row=r_idx, column=c_i, value=val)
                    c.font = font_data
                    c.border = border_all
                    if c_i == 1:
                        c.alignment = align_left
                    elif c_i in (2, 3, 4, 5):
                        c.alignment = align_center
                        c.number_format = "#,##0"
                    elif c_i == 15:
                        c.alignment = align_right
                        c.number_format = "0.00%"
                    else:
                        c.alignment = align_right
                        c.number_format = "#,##0.000"
                r_idx += 1

            # Grand Total Row (Row 9)
            tot_row = r_idx
            ws_lc.cell(row=tot_row, column=1, value="الإجمالي").font = font_total
            ws_lc.cell(row=tot_row, column=1).fill = fill_grand_total
            ws_lc.cell(row=tot_row, column=1).border = double_bottom
            for c_i in range(2, 16):
                c_let = get_column_letter(c_i)
                if c_i <= 13:
                    f_val = f"=SUM({c_let}4:{c_let}{tot_row-1})"
                elif c_i == 14:
                    f_val = f"=IF(E{tot_row}=0,0,(M{tot_row}-K{tot_row})/E{tot_row})"
                else:
                    f_val = f"=IF(M{tot_row}=0,0,H{tot_row}/M{tot_row})"
                t_c = ws_lc.cell(row=tot_row, column=c_i, value=f_val)
                t_c.font = font_total
                t_c.fill = fill_grand_total
                t_c.border = double_bottom
                t_c.alignment = align_center if c_i in (2, 3, 4, 5) else align_right
                t_c.number_format = "#,##0" if c_i in (2, 3, 4, 5) else ("0.00%" if c_i == 15 else "#,##0.000")

            for col in ws_lc.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                c_let = get_column_letter(col[0].column)
                ws_lc.column_dimensions[c_let].width = max(max_len + 4, 15)

            # Build the 5 SBU Employee Details Sheets (Matching Employee Cost.xlsx)
            sbu_sheets_cfg = [
                ("admin", "Employee Details-HO"),
                ("delta_factory", "Employee Details-Delta"),
                ("united", "Employee Details - United"),
                ("retail_amman", "Retail Amman"),
                ("retail_alhadaf", "Retail Aqaba"),
            ]
            slips_by_sbu = {k: [] for k, _ in sbu_sheets_cfg}
            for slip in payslips:
                emp = slip.employee_id
                dep = (emp and emp.department_id) or slip.department_id
                comp = (emp and emp.company_id) or slip.company_id
                sk = dash_model._classify_sbu_key(emp=emp, dep=dep, comp=comp)
                if sk in slips_by_sbu:
                    slips_by_sbu[sk].append(slip)

            for sk, sh_title in sbu_sheets_cfg:
                s_list = slips_by_sbu.get(sk, [])
                if not s_list and self.report_type != "labor_cost":
                    continue
                ws_sbu = wb.create_sheet(title=sh_title)
                ws_sbu.views.sheetView[0].showGridLines = True
                ws_sbu.sheet_view.rightToLeft = True

                sbu_headers = [
                    "الرقم الوظيفي",
                    "اسم الموظف",
                    "الإدارة",
                    "القسم",
                    "الوحدة / الفرع",
                    "الراتب الأساسي",
                    "العلاوات",
                    "العمل الاضافي",
                    "التأمين الصحي",
                    "الضمان الاجتماعي",
                    "إجمالي تكلفة الموظف",
                ]
                for c_i, h_t in enumerate(sbu_headers, start=1):
                    hc = ws_sbu.cell(row=1, column=c_i, value=h_t)
                    hc.font = font_col_header
                    hc.fill = fill_primary_header
                    hc.alignment = align_center
                    hc.border = border_all

                sr = 2
                for slip in s_list:
                    emp = slip.employee_id
                    dep = (emp and emp.department_id) or slip.department_id
                    full_path = (dep.complete_name or dep.name) if dep else ""
                    parts = [p.strip() for p in full_path.split("/") if p.strip()]
                    d_lvl1 = parts[0] if len(parts) >= 1 else ""
                    d_lvl2 = parts[1] if len(parts) >= 2 else d_lvl1
                    d_lvl3 = " / ".join(parts[2:]) if len(parts) >= 3 else (parts[-1] if parts else "")

                    c_wage = (emp and getattr(emp, "wage", 0.0)) or getattr(slip, "basic_wage", 0.0) or 0.0
                    b_sal = 0.0
                    alw_sal = 0.0
                    ot_sal = 0.0
                    med_comp = 0.0
                    has_med = False
                    ssc_emp = 0.0
                    ssc_comp = 0.0

                    for l in getattr(slip, "line_ids", []):
                        cc = (l.code or "").upper().strip()
                        cat_c = (l.category_id.code or "").upper().strip() if l.category_id else ""
                        nm = (l.name or "").lower().strip()
                        amt = l.total or 0.0

                        if cc in ("NET", "GROSS", "GRS", "TOTAL_GROSS") or cat_c in ("NET", "GROSS"):
                            continue
                        if cc in ("FULL_WAGE", "ACTUAL_SALARY", "ACTUAL") or "actual salary" in nm or "الراتب الفعلي" in nm:
                            continue
                        if cc in ("BASIC", "SALARY", "BASE", "WAGE") or cat_c == "BASIC":
                            b_sal += amt
                            continue
                        if (
                            cc in ("OT_NET", "ETH_NET", "RD-S", "OVERTIME", "GROSS_ATT", "OT_COMP", "EXTRA_HOURS", "TERM_EXTRA", "OT")
                            or any(k in cc for k in ["OT", "OVERTIME", "EXTRA"])
                            or any(k in nm for k in ["اضافي", "إضافي", "عمل إضافي", "عمل اضافي"])
                        ) and cat_c not in ("DED", "DEDUCTION"):
                            ot_sal += amt
                            continue
                        if cc in ("MED_COMP", "INS_COMP", "HEALTH_COMP") or ("تأمين صحي" in nm and ("شركة" in nm or "صاحب العمل" in nm)):
                            med_comp += abs(amt)
                            continue
                        if cc == "INS" or "تأمين صحي" in nm or "تامين صحي" in nm:
                            if abs(amt) > 0:
                                has_med = True
                        is_ss_e = cc in ("SSE", "SSCE", "SSC_EMP", "SOC_SEC_EMP") or ("ضمان" in nm and "موظف" in nm)
                        is_ss_c = cc in ("SSC", "SSCC", "SSC_COMP", "SOC_SEC_COMP") or ("ضمان" in nm and ("شركة" in nm or "صاحب العمل" in nm))
                        if is_ss_e or is_ss_c or any(k in cc for k in ["SS", "SSC", "GOSI"]) or "ضمان" in nm:
                            if is_ss_c or any(k in cc for k in ["COMP", "COMPANY", "ER", "SSCCO", "SSCP"]):
                                ssc_comp += abs(amt)
                            else:
                                ssc_emp += abs(amt)
                            continue
                        if cat_c in ("ALW", "ALLOWANCE", "ALW_RECURRING") or any(k in nm for k in ["علاوة", "مكافأة", "مكافاه", "بدل", "تكليف", "تنقل"]):
                            alw_sal += amt

                    if not b_sal:
                        b_sal = c_wage
                    if not med_comp and has_med:
                        med_comp = 13.0
                    if not ssc_comp and ssc_emp > 0:
                        ssc_comp = round(ssc_emp * (14.25 / 7.5), 3)

                    s_vals = [
                        self._get_emp_code(emp),
                        emp.name if emp else "",
                        d_lvl1,
                        d_lvl2,
                        d_lvl3,
                        round(b_sal, 3),
                        round(alw_sal, 3),
                        round(ot_sal, 3),
                        round(med_comp, 3),
                        round(ssc_comp, 3),
                        f"=SUM(F{sr}:J{sr})",
                    ]
                    for c_i, v in enumerate(s_vals, start=1):
                        sc = ws_sbu.cell(row=sr, column=c_i, value=v)
                        sc.font = font_data
                        sc.border = border_all
                        if c_i <= 5:
                            sc.alignment = align_center if c_i == 1 else align_left
                        else:
                            sc.alignment = align_right
                            sc.number_format = "#,##0.000"
                    sr += 1

                if sr > 2:
                    ws_sbu.cell(row=sr, column=1, value="Property Total").font = font_total
                    ws_sbu.cell(row=sr, column=1).fill = fill_grand_total
                    for c_i in range(6, 12):
                        c_let = get_column_letter(c_i)
                        tc = ws_sbu.cell(row=sr, column=c_i, value=f"=SUM({c_let}2:{c_let}{sr-1})")
                        tc.font = font_total
                        tc.fill = fill_grand_total
                        tc.border = double_bottom
                        tc.alignment = align_right
                        tc.number_format = "#,##0.000"

                for col in ws_sbu.columns:
                    max_len = max(len(str(cell.value or "")) for cell in col)
                    c_let = get_column_letter(col[0].column)
                    ws_sbu.column_dimensions[c_let].width = max(max_len + 4, 14)

        # -------------------------------------------------------------
        # SHEET 1: Monthly Payroll List
        # -------------------------------------------------------------
        if self.report_type in ["all", "payroll"]:
            ws_pay = wb.create_sheet(title="Monthly Payroll List")
            ws_pay.views.sheetView[0].showGridLines = True

            ws_pay.cell(row=1, column=16, value=f"Monthly Payroll List {period_title}").font = font_header_title
            ws_pay.cell(row=2, column=16, value="مياومة,عقد غير محدد المدة,عقد وزارة العمل,متدرب,عقد محدد المدة").font = font_sub_title
            ws_pay.cell(row=3, column=16, value="Final Copy-Current Employees").font = font_sub_title

            headers_group = [
                (1, 10, "Employee & Salary Information", fill_primary_header),
                (11, 17, "Allowances (العلاوات والبدلات)", fill_alw_header),
                (18, 18, "Gross Salary", fill_primary_header),
                (19, 32, "Deductions & Taxes (الخصومات والاقتطاعات)", fill_ded_header),
                (33, 33, "Net Salary", fill_primary_header),
            ]
            for start_c, end_c, title, fill in headers_group:
                if start_c != end_c:
                    ws_pay.merge_cells(start_row=5, start_column=start_c, end_row=5, end_column=end_c)
                c_cell = ws_pay.cell(row=5, column=start_c, value=title)
                c_cell.font = font_col_header
                c_cell.fill = fill
                c_cell.alignment = align_center

            cols = [
                "Property", "دائرة", "قسم", "فرع", "Emp No.", "Emp Name", 
                "Calendar Days", "Working Days", "Daily Rate (JOD/Day)", "Basic Salary", "Actual basic salary", "Due Salary",
                "علاوة تكليف", "مكافأة مالية-شهرية", "عمل اضافي", "بدل تنقلات", "عائد ضمان", "علاوات أخرى", "Total Allowances",
                "Gross Salary",
                "دفعة أولى", "دفعة ثانية", "فرق راتب", "قرض شركة", "City Ledger", "برنامج وطني", "تأمين صحي", "عقوبات وغرامات",
                "ضمان اجتماعي", "ضريبة الدخل", "مخالفات وخصومات", "خصم ساعات", "سلف أخرى", "Total Deductions",
                "Net Salary"
            ]
            for idx, col_name in enumerate(cols, start=1):
                cell = ws_pay.cell(row=6, column=idx, value=col_name)
                cell.font = font_sub_header
                cell.fill = fill_sub_header
                cell.alignment = align_center
                cell.border = border_all

            row_idx = 7
            cal_days = (self.date_to - self.date_from).days + 1 if self.date_to and self.date_from else 30
            if cal_days <= 0: cal_days = 30

            for slip in payslips:
                emp = slip.employee_id
                dep = (emp and emp.department_id) or slip.department_id or (getattr(slip, "version_id", False) and slip.version_id.department_id)
                full_dept_path = (dep.complete_name or dep.name) if dep else _("Unassigned")
                path_parts = [p.strip() for p in full_dept_path.split("/") if p.strip()]
                division_name = path_parts[0] if len(path_parts) >= 1 else _("Unassigned")
                dept_name = " / ".join(path_parts[1:-1]) if len(path_parts) >= 3 else (path_parts[1] if len(path_parts) == 2 else division_name)
                branch_name = path_parts[-1] if len(path_parts) >= 1 else (getattr(emp, "work_location_id", False) and emp.work_location_id.name or division_name)

                contract_w = (
                    (emp and getattr(emp, "wage", 0.0))
                    or getattr(slip, "basic_wage", 0.0)
                    or getattr(slip, "wage", 0.0)
                    or (slip.contract_id and slip.contract_id.wage)
                    or (slip.version_id and getattr(slip.version_id, "contract_wage", 0.0))
                    or 0.0
                )
                basic_w = 0.0
                actual_w = 0.0
                due_w = 0.0

                alw_takleef = 0.0
                alw_bonus = 0.0
                alw_ot = 0.0
                alw_trans = 0.0
                alw_ss = 0.0
                alw_other = 0.0

                ded_pay1 = 0.0
                ded_pay2 = 0.0
                ded_diff = 0.0
                ded_loan = 0.0
                ded_city = 0.0
                ded_nat = 0.0
                ded_ins = 0.0
                ded_pen = 0.0
                ded_ss = 0.0
                ded_tax = 0.0
                ded_viol = 0.0
                ded_hours = 0.0
                ded_other = 0.0

                gross_val = getattr(slip, "gross_wage", 0.0) or 0.0
                net_val = getattr(slip, "net_wage", 0.0) or 0.0

                if hasattr(slip, "line_ids") and slip.line_ids:
                    for l in slip.line_ids:
                        c_code = (l.code or "").upper().strip()
                        c_name = (l.name or "").lower()
                        amt = l.total or 0.0

                        is_actual = c_code in ("FULL_WAGE", "ACTUAL_SALARY", "ACTUAL") or "actual salary" in c_name or "الراتب الفعلي" in c_name
                        is_basic = c_code in ("BASIC", "SALARY", "BASE", "WAGE") and not is_actual

                        if c_code == "NET": net_val = amt
                        elif c_code in ["GROSS", "GRS", "TOTAL_GROSS"]: gross_val = amt
                        elif is_basic: basic_w += amt
                        elif is_actual: actual_w += amt
                        elif "تكليف" in c_name: alw_takleef += amt
                        elif "مكافأة" in c_name or "مكافاه" in c_name: alw_bonus += amt
                        elif "إضافي" in c_name or "اضافي" in c_name or "OT" in c_code or c_code in ("OT_NET", "ETH_NET", "RD-S", "TERM_EXTRA"): alw_ot += amt
                        elif "تنقل" in c_name or "مواصلات" in c_name: alw_trans += amt
                        elif "عائد ضمان" in c_name: alw_ss += amt
                        elif (l.category_id and l.category_id.code in ["ALW", "ALLOWANCE"]) and c_code not in ["NET", "GROSS", "BASIC", "ACTUAL", "FULL_WAGE"]:
                            alw_other += amt
                        
                        elif "دفعة اولى" in c_name or "دفعة 1" in c_name: ded_pay1 += abs(amt)
                        elif "دفعة ثانية" in c_name or "دفعة 2" in c_name: ded_pay2 += abs(amt)
                        elif "فرق راتب" in c_name: ded_diff += abs(amt)
                        elif "قرض" in c_name or "سلفة" in c_name or "LOAN" in c_code: ded_loan += abs(amt)
                        elif "city ledger" in c_name: ded_city += abs(amt)
                        elif "وطني" in c_name: ded_nat += abs(amt)
                        elif "تأمين" in c_name or "تامين" in c_name: ded_ins += abs(amt)
                        elif "عقوبات" in c_name or "غرامات" in c_name: ded_pen += abs(amt)
                        elif ("ضمان" in c_name or "SS" in c_code or "SSC" in c_code) and c_code not in ("SSC", "SSCC", "SSC_COMP", "SOC_SEC_COMP") and "شركة" not in c_name:
                            ded_ss += abs(amt)
                        elif "ضريبة" in c_name or "TAX" in c_code: ded_tax += abs(amt)
                        elif "مخالفات" in c_name: ded_viol += abs(amt)
                        elif "خصم ساعات" in c_name or "تأخير" in c_name or "LATE" in c_code or c_code == "DED_UNDERTIME": ded_hours += abs(amt)
                        elif (l.category_id and l.category_id.code in ["DED", "DEDUCTION"]) and c_code not in ["NET", "GROSS"]:
                            ded_other += abs(amt)

                if not basic_w: basic_w = contract_w
                if not actual_w: actual_w = basic_w
                due_w = actual_w

                tot_alw = alw_takleef + alw_bonus + alw_ot + alw_trans + alw_ss + alw_other
                tot_ded = ded_pay1 + ded_pay2 + ded_diff + ded_loan + ded_city + ded_nat + ded_ins + ded_pen + ded_ss + ded_tax + ded_viol + ded_hours + ded_other
                if not gross_val: gross_val = actual_w + tot_alw
                if not net_val: net_val = gross_val - tot_ded

                daily_rate = round((gross_val + (ded_ss * 1.9)) / float(cal_days), 3)

                w_days = 30.0
                if hasattr(slip, "worked_days_line_ids") and slip.worked_days_line_ids:
                    w_days = sum(wd.number_of_days for wd in slip.worked_days_line_ids if wd.code != "OUT") or 30.0

                row_values = [
                    self.company_id.name,
                    division_name,
                    dept_name,
                    branch_name,
                    self._get_emp_code(emp),
                    emp.name,
                    cal_days,
                    round(w_days, 2),
                    daily_rate,
                    round(basic_w, 3),
                    round(actual_w, 3),
                    round(due_w, 3),
                    round(alw_takleef, 3),
                    round(alw_bonus, 3),
                    round(alw_ot, 3),
                    round(alw_trans, 3),
                    round(alw_ss, 3),
                    round(alw_other, 3),
                    round(tot_alw, 3),
                    round(gross_val, 3),
                    round(ded_pay1, 3),
                    round(ded_pay2, 3),
                    round(ded_diff, 3),
                    round(ded_loan, 3),
                    round(ded_city, 3),
                    round(ded_nat, 3),
                    round(ded_ins, 3),
                    round(ded_pen, 3),
                    round(ded_ss, 3),
                    round(ded_tax, 3),
                    round(ded_viol, 3),
                    round(ded_hours, 3),
                    round(ded_other, 3),
                    round(tot_ded, 3),
                    round(net_val, 3),
                ]


                for col_i, val in enumerate(row_values, start=1):
                    c = ws_pay.cell(row=row_idx, column=col_i, value=val)
                    c.font = font_data
                    c.border = border_all
                    if isinstance(val, (int, float)):
                        c.alignment = align_right
                        c.number_format = "#,##0.000" if col_i not in [7] else "0.00"
                    else:
                        c.alignment = align_left

                row_idx += 1

            ws_pay.cell(row=row_idx, column=5, value="Grand Total").font = font_total
            ws_pay.cell(row=row_idx, column=5).fill = fill_grand_total
            for col_i in range(7, 34):
                col_letter = get_column_letter(col_i)
                sum_cell = ws_pay.cell(row=row_idx, column=col_i, value=f"=SUM({col_letter}7:{col_letter}{row_idx-1})")
                sum_cell.font = font_total
                sum_cell.fill = fill_grand_total
                sum_cell.border = double_bottom
                sum_cell.alignment = align_right
                sum_cell.number_format = "#,##0.000" if col_i != 7 else "0.00"

            for col in ws_pay.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                col_letter = get_column_letter(col[0].column)
                ws_pay.column_dimensions[col_letter].width = max(max_len + 3, 12)

        # -------------------------------------------------------------
        # SHEET 2: Monthly Overtime Analysis
        # -------------------------------------------------------------
        if self.report_type in ["all", "overtime"]:
            ws_ot = wb.create_sheet(title="Monthly Overtime")
            ws_ot.views.sheetView[0].showGridLines = True

            ws_ot.cell(row=1, column=1, value=f"Monthly Overtime {period_title}").font = font_header_title
            ws_ot.cell(row=2, column=1, value="Final Copy").font = font_sub_title

            ot_headers = [
                "Emp No.", "Emp Name", "Department / Branch", "Document Ref", "OT Date",
                "Overtime Rate", "Pay Rate / Hr", "Salary", "Accrued Hours", "Paid Hours", "Days", "Amount"
            ]
            for c_i, h_name in enumerate(ot_headers, start=1):
                cell = ws_ot.cell(row=5, column=c_i, value=h_name)
                cell.font = font_col_header
                cell.fill = fill_primary_header
                cell.alignment = align_center
                cell.border = border_all

            ot_row = 6
            for slip in payslips:
                emp = slip.employee_id
                dep = (emp and emp.department_id) or slip.department_id
                dept_name = (dep.complete_name or dep.name) if dep else ""
                basic_w = (emp and getattr(emp, "wage", 0.0)) or getattr(slip, "basic_wage", 0.0) or getattr(slip, "wage", 0.0) or 0.0
                if hasattr(slip, "line_ids") and slip.line_ids:
                    b_lines = slip.line_ids.filtered(lambda l: (l.code or "").upper() in ("BASIC", "SALARY", "BASE", "WAGE"))
                    if b_lines:
                        basic_w = sum(b_lines.mapped("total")) or basic_w
                pay_rate = round(basic_w / 240.0, 3) if basic_w else 0.0

                ot_hours = float(getattr(slip, "attendance_gross_overtime", 0.0) or getattr(slip, "extra_hours_R", 0.0) or 0.0)
                ot_amt = 0.0
                if hasattr(slip, "worked_days_line_ids") and slip.worked_days_line_ids:
                    wd_ot_hrs = sum(wd.number_of_hours for wd in slip.worked_days_line_ids if "OT" in (wd.code or "").upper() or "EXTRA" in (wd.code or "").upper() or "اضافي" in (wd.name or "") or "إضافي" in (wd.name or ""))
                    if wd_ot_hrs > ot_hours:
                        ot_hours = wd_ot_hrs
                
                if hasattr(slip, "line_ids") and slip.line_ids:
                    ot_amt = sum(l.total for l in slip.line_ids if (l.code or "").upper() in ("OT_NET", "ETH_NET", "RD-S", "TERM_EXTRA", "OVERTIME", "OT") or "OT" in (l.code or "").upper() or "OVERTIME" in (l.code or "").upper() or "اضافي" in (l.name or "") or "إضافي" in (l.name or ""))
                
                if not ot_amt and ot_hours:
                    ot_amt = round(ot_hours * pay_rate * 1.25, 3)

                ot_vals = [
                    self._get_emp_code(emp),
                    emp.name,
                    dept_name,
                    slip.number or slip.name or "OT-RUN",
                    str(slip.date_to or self.date_to),
                    1.25,
                    pay_rate,
                    round(basic_w, 3),
                    round(ot_hours, 2),
                    round(ot_hours, 2),
                    round(ot_hours / 8.0, 2),
                    round(ot_amt, 3),
                ]

                for col_i, val in enumerate(ot_vals, start=1):
                    c = ws_ot.cell(row=ot_row, column=col_i, value=val)
                    c.font = font_data
                    c.border = border_all
                    if isinstance(val, (int, float)):
                        c.alignment = align_right
                        c.number_format = "#,##0.000" if col_i in [7, 8, 12] else "0.00"
                    else:
                        c.alignment = align_left
                ot_row += 1

            ws_ot.cell(row=ot_row, column=2, value="Total Overtime").font = font_total
            ws_ot.cell(row=ot_row, column=2).fill = fill_grand_total
            for col_i in [9, 10, 11, 12]:
                c_let = get_column_letter(col_i)
                sum_cell = ws_ot.cell(row=ot_row, column=col_i, value=f"=SUM({c_let}6:{c_let}{ot_row-1})")
                sum_cell.font = font_total
                sum_cell.fill = fill_grand_total
                sum_cell.border = double_bottom
                sum_cell.alignment = align_right
                sum_cell.number_format = "#,##0.000" if col_i == 12 else "0.00"

            for col in ws_ot.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                c_let = get_column_letter(col[0].column)
                ws_ot.column_dimensions[c_let].width = max(max_len + 3, 12)

        # -------------------------------------------------------------
        # SHEET 3: Bank Transfer File (Exact Bank Format)
        # -------------------------------------------------------------
        if self.report_type in ["all", "bank"]:
            ws_bank = wb.create_sheet(title="Bank File Factory")
            ws_bank.views.sheetView[0].showGridLines = True

            bank_row = 1
            src_acc = self.company_source_account or "0126046919500"
            val_date = (self.date_to + timedelta(days=5)).strftime("%d/%m/%Y")
            desc_text = f"SALARY PAYMENT {self.date_to.strftime('%m %Y')}"

            for slip in payslips:
                emp = slip.employee_id
                net_amt = getattr(slip, "net_wage", 0.0) or 0.0
                if hasattr(slip, "line_ids") and slip.line_ids:
                    net_line = slip.line_ids.filtered(lambda l: l.code == "NET")
                    if net_line:
                        net_amt = net_line[0].total

                bank_acc = emp.bank_account_id or (getattr(emp, "bank_account_ids", False) and emp.bank_account_ids[0])
                acc_num = bank_acc.acc_number if bank_acc else ""
                bic = bank_acc.bank_id.bic if bank_acc and bank_acc.bank_id else "ARABJOAXXXX"
                if not bic: bic = "ARABJOAXXXX"

                txn_type = "LBT" if (acc_num and acc_num.strip().upper().startswith("JO")) else "BT"
                emp_name_en = self._get_emp_name_en(emp) or emp.name

                b_vals = [
                    txn_type,
                    src_acc,
                    acc_num or "CASH_NO_IBAN",
                    emp_name_en.upper(),
                    bic.upper(),
                    "13",
                    val_date,
                    "JOD",
                    round(net_amt, 3),
                    "",
                    "",
                    desc_text,
                    self._get_emp_code(emp),
                ]

                for col_i, val in enumerate(b_vals, start=1):
                    c = ws_bank.cell(row=bank_row, column=col_i, value=val)
                    c.font = font_data
                    if isinstance(val, (int, float)):
                        c.alignment = align_right
                        c.number_format = "0.000"
                    else:
                        c.alignment = align_left

                bank_row += 1

            for col in ws_bank.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                c_let = get_column_letter(col[0].column)
                ws_bank.column_dimensions[c_let].width = max(max_len + 2, 14)

        # -------------------------------------------------------------
        # SHEET 4: Attendance Reconciliation
        # -------------------------------------------------------------
        if self.report_type in ["all", "attendance"]:
            ws_att = wb.create_sheet(title="Attendance Reconciliation")
            ws_att.views.sheetView[0].showGridLines = True

            ws_att.cell(row=1, column=1, value="Attendance Reconciliation").font = font_header_title
            ws_att.cell(row=2, column=1, value=f"Period: {self.date_from} to {self.date_to}").font = font_sub_title

            att_headers = [
                "Number", "Name", "Department", "Scheduled Hours", "Approved Hours",
                "Extra Hours", "Subtractive Hours", "Reconciliation Hours"
            ]
            for c_i, h_name in enumerate(att_headers, start=1):
                cell = ws_att.cell(row=4, column=c_i, value=h_name)
                cell.font = font_col_header
                cell.fill = fill_primary_header
                cell.alignment = align_center
                cell.border = border_all

            att_row = 5
            for slip in payslips:
                emp = slip.employee_id
                dep = (emp and emp.department_id) or slip.department_id
                dept_name = (dep.complete_name or dep.name) if dep else ""

                w_days = 0.0
                sched_hrs = 0.0
                ot_hrs = 0.0
                late_hrs = 0.0

                if hasattr(slip, "worked_days_line_ids") and slip.worked_days_line_ids:
                    for wd in slip.worked_days_line_ids:
                        code = (wd.code or "").upper().strip()
                        name = (wd.name or "").lower()
                        hrs = wd.number_of_hours or 0.0
                        days = wd.number_of_days or 0.0

                        is_ot = any(k in code for k in ["OT", "EXTRA", "OVERTIME"]) or any(k in name for k in ["إضافي", "اضافي"])
                        is_late = any(k in code for k in ["LATE", "UNPAID", "ABSENT", "SHORT", "DELAY", "DED_HOURS"]) or any(k in name for k in ["تأخير", "تاخير", "خصم ساعات", "غياب", "مغادرة"])

                        if is_ot:
                            ot_hrs += hrs
                        elif is_late:
                            late_hrs += hrs
                        else:
                            if code not in ["OUT"]:
                                w_days += days
                                sched_hrs += hrs if hrs > 0 else (days * 8.0)

                pfr_ot_hrs = float(getattr(slip, "attendance_gross_overtime", 0.0) or getattr(slip, "extra_hours_R", 0.0) or 0.0)
                pfr_late_hrs = float(getattr(slip, "attendance_gross_undertime", 0.0) or getattr(slip, "lateness_deducted_cash", 0.0) or 0.0)
                if pfr_ot_hrs > ot_hrs:
                    ot_hrs = pfr_ot_hrs
                if pfr_late_hrs > late_hrs:
                    late_hrs = pfr_late_hrs

                if not sched_hrs:
                    sched_hrs = (w_days * 8.0) if w_days else 240.0
                approved_hrs = round(max(sched_hrs + ot_hrs - late_hrs, 0.0), 2)
                recon_hrs = round(ot_hrs - late_hrs, 2)

                def _fmt_hrs(val):
                    sign = "-" if val < 0 else ""
                    val = abs(val)
                    h = int(val)
                    m = int(round((val - h) * 60))
                    return f"{sign}{h:02d}:{m:02d}"

                att_vals = [
                    self._get_emp_code(emp),
                    emp.name,
                    dept_name,
                    _fmt_hrs(sched_hrs),
                    _fmt_hrs(approved_hrs),
                    _fmt_hrs(ot_hrs),
                    _fmt_hrs(late_hrs),
                    _fmt_hrs(recon_hrs),
                ]

                for col_i, val in enumerate(att_vals, start=1):
                    c = ws_att.cell(row=att_row, column=col_i, value=val)
                    c.font = font_data
                    c.border = border_all
                    c.alignment = align_center if col_i in [1, 4, 5, 6, 7, 8] else align_left

                att_row += 1

            for col in ws_att.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                c_let = get_column_letter(col[0].column)
                ws_att.column_dimensions[c_let].width = max(max_len + 3, 14)

        fp = io.BytesIO()
        wb.save(fp)
        fp.seek(0)
        file_data = base64.b64encode(fp.read())
        fp.close()

        file_name = f"HR_Payroll_Unified_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        self.write({
            "excel_file": file_data,
            "file_name": file_name,
        })

        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/?model=hr.payroll.report.wizard&id={self.id}&field=excel_file&download=true&filename={file_name}",
            "target": "self",
        }
