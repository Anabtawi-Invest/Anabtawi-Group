# -*- coding: utf-8 -*-
import io
import xlsxwriter

COLUMNS = [
    ('branch_code', 'Branch Code / كود الفرع', 18, 'text'),
    ('branch_name', 'Branch Name / اسم الفرع', 32, 'text'),
    ('sales_profit', 'Sales Revenue / أرباح المبيعات', 22, 'currency'),
    ('employee_count', 'Employees / عدد الموظفين', 18, 'integer'),
    ('attendance_days', 'Attendance Days / أيام الدوام', 20, 'number'),
    ('labor_cost', 'Labor Cost / تكلفة الموظفين', 22, 'cost'),
    ('approved_ot_hours', 'Approved OT (hrs) / أوفر تايم معتمد', 22, 'number'),
    ('unapproved_ot_hours', 'Unapproved OT (hrs) / أوفر تايم غير معتمد', 22, 'number'),
    ('total_ot_hours', 'Total OT (hrs) / إجمالي الأوفر تايم', 22, 'number'),
    ('net_margin', 'Net Margin / صافي الهامش', 22, 'margin'),
    ('labor_pct', 'Labor Cost % / نسبة تكلفة العمالة', 20, 'percent'),
    ('pos_config_names', 'Linked POS / نقاط البيع المرتبطة', 28, 'text'),
    ('notes', 'Notes / ملاحظات', 35, 'text'),
]

def build_retail_labor_cost_xlsx(rows, metadata):
    buffer = io.BytesIO()
    book = xlsxwriter.Workbook(
        buffer,
        {'in_memory': True, 'strings_to_formulas': False, 'strings_to_urls': False}
    )
    sheet = book.add_worksheet('Retail Labor Cost')
    sheet.hide_gridlines(2)
    sheet.set_landscape()
    sheet.set_paper(9)  # A4
    sheet.fit_to_pages(1, 0)
    sheet.set_zoom(90)

    # Styles
    title_fmt = book.add_format({
        'bold': True, 'font_size': 18, 'font_color': '#17365D', 'font_name': 'Segoe UI'
    })
    subtitle_fmt = book.add_format({
        'font_size': 11, 'font_color': '#4A5568', 'font_name': 'Segoe UI'
    })
    info_fmt = book.add_format({
        'font_size': 10, 'font_color': '#718096', 'font_name': 'Segoe UI'
    })

    # KPI Summary Card Styles
    kpi_box = {'border': 1, 'border_color': '#CBD5E1', 'valign': 'vcenter', 'align': 'center'}
    kpi_title_fmt = book.add_format(dict(kpi_box, bold=True, font_size=9, bg_color='#F1F5F9', font_color='#475569'))
    kpi_val_sales = book.add_format(dict(kpi_box, bold=True, font_size=12, bg_color='#EFF6FF', font_color='#1D4ED8', num_format='#,##0.000'))
    kpi_val_cost = book.add_format(dict(kpi_box, bold=True, font_size=12, bg_color='#FEF2F2', font_color='#B91C1C', num_format='#,##0.000'))
    kpi_val_ot_app = book.add_format(dict(kpi_box, bold=True, font_size=12, bg_color='#ECFDF5', font_color='#047857', num_format='#,##0.00'))
    kpi_val_ot_unapp = book.add_format(dict(kpi_box, bold=True, font_size=12, bg_color='#FFFBEB', font_color='#B45309', num_format='#,##0.00'))

    header_fmt = book.add_format({
        'bold': True, 'bg_color': '#17365D', 'font_color': '#FFFFFF',
        'text_wrap': True, 'valign': 'vcenter', 'align': 'center',
        'border': 1, 'border_color': '#0F243E', 'font_name': 'Segoe UI', 'font_size': 10
    })

    base_cell = {
        'font_name': 'Segoe UI', 'font_size': 10, 'border': 1,
        'border_color': '#E2E8F0', 'valign': 'vcenter'
    }
    text_fmt = book.add_format(dict(base_cell, align='left', text_wrap=True))
    text_center_fmt = book.add_format(dict(base_cell, align='center'))
    int_fmt = book.add_format(dict(base_cell, align='center', num_format='#,##0'))
    num_fmt = book.add_format(dict(base_cell, align='right', num_format='#,##0.00'))
    curr_fmt = book.add_format(dict(base_cell, align='right', num_format='#,##0.000'))
    cost_fmt = book.add_format(dict(base_cell, bold=True, align='right', bg_color='#FFF5F5', font_color='#991B1B', num_format='#,##0.000'))
    margin_fmt = book.add_format(dict(base_cell, bold=True, align='right', bg_color='#F0FDF4', font_color='#15803D', num_format='#,##0.000'))
    pct_fmt = book.add_format(dict(base_cell, bold=True, align='right', num_format='0.0%'))

    total_fmt = book.add_format({
        'bold': True, 'bg_color': '#E8EEF5', 'font_color': '#0F172A',
        'font_name': 'Segoe UI', 'font_size': 10, 'border': 1,
        'border_color': '#CBD5E1', 'valign': 'vcenter', 'align': 'right',
        'num_format': '#,##0.000'
    })
    total_num_fmt = book.add_format({
        'bold': True, 'bg_color': '#E8EEF5', 'font_color': '#0F172A',
        'font_name': 'Segoe UI', 'font_size': 10, 'border': 1,
        'border_color': '#CBD5E1', 'valign': 'vcenter', 'align': 'right',
        'num_format': '#,##0.00'
    })
    total_int_fmt = book.add_format({
        'bold': True, 'bg_color': '#E8EEF5', 'font_color': '#0F172A',
        'font_name': 'Segoe UI', 'font_size': 10, 'border': 1,
        'border_color': '#CBD5E1', 'valign': 'vcenter', 'align': 'center',
        'num_format': '#,##0'
    })
    total_label_fmt = book.add_format({
        'bold': True, 'bg_color': '#E8EEF5', 'font_color': '#0F172A',
        'font_name': 'Segoe UI', 'font_size': 10, 'border': 1,
        'border_color': '#CBD5E1', 'valign': 'vcenter', 'align': 'center'
    })

    # Header section
    sheet.merge_range('A1:G1', 'RETAIL LABOR COST & SALES PROFIT REPORT | تقرير تكلفة عمالة وأرباح أفرع الريتيل', title_fmt)
    sheet.merge_range('A2:G2', f"Company: {metadata.get('company', '')}  |  Period: {metadata.get('period', '')}  |  Pay Run: {metadata.get('payrun', 'All')}", subtitle_fmt)
    sheet.merge_range('A3:G3', f"Generated by: {metadata.get('user', '')}  |  Date: {metadata.get('generated', '')}  |  Currency: {metadata.get('currency', 'JOD')}", info_fmt)

    # KPI Banner (Row 4 & 5)
    tot_sales = sum(r.get('sales_profit', 0.0) for r in rows)
    tot_cost = sum(r.get('labor_cost', 0.0) for r in rows)
    tot_ot_app = sum(r.get('approved_ot_hours', 0.0) for r in rows)
    tot_ot_unapp = sum(r.get('unapproved_ot_hours', 0.0) for r in rows)

    sheet.write('A4', 'TOTAL SALES / إجمالي مبيعات الأفرع', kpi_title_fmt)
    sheet.write('A5', tot_sales, kpi_val_sales)

    sheet.write('B4', 'TOTAL LABOR COST / إجمالي تكلفة الموظفين', kpi_title_fmt)
    sheet.write('B5', tot_cost, kpi_val_cost)

    sheet.write('C4', 'APPROVED OT / أوفر تايم معتمد', kpi_title_fmt)
    sheet.write('C5', f'{tot_ot_app:,.2f} Hrs', kpi_val_ot_app)

    sheet.write('D4', 'UNAPPROVED OT / أوفر تايم غير معتمد', kpi_title_fmt)
    sheet.write('D5', f'{tot_ot_unapp:,.2f} Hrs', kpi_val_ot_unapp)

    sheet.set_row(3, 20)
    sheet.set_row(4, 26)

    # Table Header (Row 7)
    header_row = 6
    sheet.set_row(header_row, 45)
    for col_idx, (_, label, width, _) in enumerate(COLUMNS):
        sheet.set_column(col_idx, col_idx, width)
        sheet.write_string(header_row, col_idx, label, header_fmt)

    # Data Rows
    first_data_row = header_row + 1
    for r_idx, row_data in enumerate(rows, first_data_row):
        sheet.set_row(r_idx, 28)
        for c_idx, (key, _, _, kind) in enumerate(COLUMNS):
            val = row_data.get(key)
            if val is None or val == '':
                sheet.write_blank(r_idx, c_idx, None, text_fmt if kind == 'text' else curr_fmt)
            elif kind == 'text':
                sheet.write_string(r_idx, c_idx, str(val), text_center_fmt if c_idx == 0 else text_fmt)
            elif kind == 'integer':
                sheet.write_number(r_idx, c_idx, int(val), int_fmt)
            elif kind == 'number':
                sheet.write_number(r_idx, c_idx, float(val), num_fmt)
            elif kind == 'currency':
                sheet.write_number(r_idx, c_idx, float(val), curr_fmt)
            elif kind == 'cost':
                sheet.write_number(r_idx, c_idx, float(val), cost_fmt)
            elif kind == 'margin':
                sheet.write_number(r_idx, c_idx, float(val), margin_fmt)
            elif kind == 'percent':
                sheet.write_number(r_idx, c_idx, float(val) / 100.0 if float(val) > 1.0 else float(val), pct_fmt)

    last_data_row = first_data_row + len(rows) - 1

    # Autofilter & Panes
    if rows:
        sheet.autofilter(header_row, 0, last_data_row, len(COLUMNS) - 1)
        sheet.freeze_panes(first_data_row, 2)

    # Totals Row
    totals_row = last_data_row + 1 if rows else first_data_row
    sheet.set_row(totals_row, 30)
    sheet.merge_range(totals_row, 0, totals_row, 1, 'TOTAL / الإجمالي العام', total_label_fmt)

    for c_idx, (key, _, _, kind) in enumerate(COLUMNS):
        if c_idx < 2:
            continue
        col_letter = xlsxwriter.utility.xl_col_to_name(c_idx)
        if kind == 'integer':
            if rows:
                formula = f'=SUBTOTAL(109,{col_letter}{first_data_row + 1}:{col_letter}{last_data_row + 1})'
                val_sum = sum(row.get(key, 0) or 0 for row in rows)
                sheet.write_formula(totals_row, c_idx, formula, total_int_fmt, val_sum)
            else:
                sheet.write_number(totals_row, c_idx, 0, total_int_fmt)
        elif kind == 'number':
            if rows:
                formula = f'=SUBTOTAL(109,{col_letter}{first_data_row + 1}:{col_letter}{last_data_row + 1})'
                val_sum = sum(row.get(key, 0.0) or 0.0 for row in rows)
                sheet.write_formula(totals_row, c_idx, formula, total_num_fmt, val_sum)
            else:
                sheet.write_number(totals_row, c_idx, 0.0, total_num_fmt)
        elif kind in ('currency', 'cost', 'margin'):
            if rows:
                formula = f'=SUBTOTAL(109,{col_letter}{first_data_row + 1}:{col_letter}{last_data_row + 1})'
                val_sum = sum(row.get(key, 0.0) or 0.0 for row in rows)
                sheet.write_formula(totals_row, c_idx, formula, total_fmt, val_sum)
            else:
                sheet.write_number(totals_row, c_idx, 0.0, total_fmt)
        elif kind == 'percent':
            # Overall Labor % = Total Labor Cost / Total Sales
            sales_col = xlsxwriter.utility.xl_col_to_name(2)
            cost_col = xlsxwriter.utility.xl_col_to_name(5)
            formula = f'=IF({sales_col}{totals_row+1}>0,{cost_col}{totals_row+1}/{sales_col}{totals_row+1},0)'
            overall_pct = (tot_cost / tot_sales) if tot_sales > 0 else 0.0
            sheet.write_formula(totals_row, c_idx, formula, pct_fmt, overall_pct)
        else:
            sheet.write_blank(totals_row, c_idx, None, total_fmt)

    sheet.print_area(0, 0, totals_row, len(COLUMNS) - 1)
    sheet.set_footer('&LRetail Labor Cost Report&CPage &P of &N')
    book.close()
    return buffer.getvalue()
