# -*- coding: utf-8 -*-
import base64
import io
from datetime import datetime

from odoo import models, fields, api, _
from odoo.exceptions import UserError

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
except ImportError:
    openpyxl = None


class OnlineSalesReportWizard(models.TransientModel):
    _name = "online.sales.report.wizard"
    _description = "Online & Delivery Sales Excel Report Wizard"

    date_from = fields.Date(string="Start Date", required=True, default=lambda self: fields.Date.today().replace(day=1))
    date_to = fields.Date(string="End Date", required=True, default=lambda self: fields.Date.today())
    config_ids = fields.Many2many("pos.config", string="POS Branches", help="Filter by specific POS branches")
    channel_ids = fields.Many2many("online.sales.channel", string="Channels", help="Filter by specific online channels")

    def action_export_excel(self):
        """Generates and downloads the Online & Delivery Sales Excel report."""
        self.ensure_one()
        if not openpyxl:
            raise UserError(_("The 'openpyxl' Python library is required to generate Excel reports."))

        # Get Dashboard data from model engine
        DashEngine = self.env["online.sales.dashboard"]
        data = DashEngine.get_online_dashboard_data(
            date_from=self.date_from,
            date_to=self.date_to,
            config_ids=self.config_ids.ids if self.config_ids else None,
            channel_ids=self.channel_ids.ids if self.channel_ids else None,
        )

        summary = data["summary"]
        channels = data["channel_breakdown"]
        branches = data["branch_breakdown"]

        wb = openpyxl.Workbook()
        
        # Styles
        title_fill = PatternFill(start_color="0083B0", end_color="0083B0", fill_type="solid")
        header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        card_fill = PatternFill(start_color="F2F4F7", end_color="F2F4F7", fill_type="solid")
        
        font_title = Font(name="Calibri", size=16, bold=True, color="FFFFFF")
        font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        font_bold = Font(name="Calibri", size=11, bold=True)
        font_card_num = Font(name="Calibri", size=14, bold=True, color="0083B0")
        
        align_center = Alignment(horizontal="center", vertical="center")
        align_right = Alignment(horizontal="right", vertical="center")
        align_left = Alignment(horizontal="left", vertical="center")
        
        thin_border = Border(
            left=Side(style="thin", color="D3D3D3"),
            right=Side(style="thin", color="D3D3D3"),
            top=Side(style="thin", color="D3D3D3"),
            bottom=Side(style="thin", color="D3D3D3")
        )

        # -------------------------------------------------------------
        # SHEET 1: Executive Dashboard Summary
        # -------------------------------------------------------------
        ws1 = wb.active
        ws1.title = "Executive Summary"
        ws1.views.sheetView[0].showGridLines = True

        # Header Title
        ws1.merge_cells("A1:G2")
        title_cell = ws1["A1"]
        title_cell.value = f"Online & Delivery Sales Breakdown ({self.date_from} to {self.date_to})"
        title_cell.fill = title_fill
        title_cell.font = font_title
        title_cell.alignment = align_center

        # Summary KPI Cards (Row 4-6)
        kpi_cards = [
            ("A4:B5", "Gross Sales", f"{summary['total_gross_sales']:.3f} JOD"),
            ("C4:D5", "Est. Commission", f"{summary['total_commission']:.3f} JOD"),
            ("E4:F5", "Net Revenue", f"{summary['net_sales']:.3f} JOD"),
            ("G4:G5", "Total Orders", str(summary["total_orders_count"])),
        ]

        # Channel Breakdown Table (Row 8)
        ws1.cell(row=8, column=1, value="Online Delivery Channel Breakdown").font = font_bold
        headers_ch = ["Channel Code", "Channel Name", "Gross Sales (JOD)", "Est. Commission", "Net Revenue", "Order Count", "% Share"]
        ws1.append([]) # Row 9 empty
        ws1.append(headers_ch) # Row 10
        for col_idx in range(1, 8):
            c = ws1.cell(row=10, column=col_idx)
            c.fill = header_fill
            c.font = font_header
            c.alignment = align_center

        row_idx = 11
        for ch in channels:
            ws1.cell(row=row_idx, column=1, value=ch["code"]).alignment = align_left
            ws1.cell(row=row_idx, column=2, value=ch["name"]).alignment = align_left
            ws1.cell(row=row_idx, column=3, value=ch["gross_amount"]).number_format = "#,##0.000"
            ws1.cell(row=row_idx, column=4, value=ch["commission_amount"]).number_format = "#,##0.000"
            ws1.cell(row=row_idx, column=5, value=ch["net_amount"]).number_format = "#,##0.000"
            ws1.cell(row=row_idx, column=6, value=ch["order_count"]).alignment = align_right
            ws1.cell(row=row_idx, column=7, value=f"{ch['percentage']}%").alignment = align_right
            row_idx += 1

        # Branch Breakdown Table
        row_idx += 2
        ws1.cell(row=row_idx, column=1, value="Branch Delivery Performance").font = font_bold
        row_idx += 1
        headers_br = ["Branch Name", "Gross Sales (JOD)", "Total Delivery Orders", "Avg Order Value"]
        ws1.append([""] * 7)
        ws1.append(headers_br)
        row_idx += 1
        for col_idx in range(1, 5):
            c = ws1.cell(row=row_idx, column=col_idx)
            c.fill = header_fill
            c.font = font_header
            c.alignment = align_center

        row_idx += 1
        for b in branches:
            aov = float_round(b["gross_amount"] / b["order_count"], precision_digits=3) if b["order_count"] > 0 else 0.0
            ws1.cell(row=row_idx, column=1, value=b["branch_name"]).alignment = align_left
            ws1.cell(row=row_idx, column=2, value=b["gross_amount"]).number_format = "#,##0.000"
            ws1.cell(row=row_idx, column=3, value=b["order_count"]).alignment = align_right
            ws1.cell(row=row_idx, column=4, value=aov).number_format = "#,##0.000"
            row_idx += 1

        # Adjust Column Widths
        ws1.column_dimensions["A"].width = 20
        ws1.column_dimensions["B"].width = 30
        ws1.column_dimensions["C"].width = 20
        ws1.column_dimensions["D"].width = 20
        ws1.column_dimensions["E"].width = 20
        ws1.column_dimensions["F"].width = 16
        ws1.column_dimensions["G"].width = 16

        # Output Stream
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        file_data = base64.b64encode(output.read())

        filename = f"Online_Sales_Report_{self.date_from}_to_{self.date_to}.xlsx"
        attachment = self.env["ir.attachment"].create({
            "name": filename,
            "type": "binary",
            "datas": file_data,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })

        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }
