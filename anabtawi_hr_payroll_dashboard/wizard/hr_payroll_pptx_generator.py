# -*- coding: utf-8 -*-
import io
import zipfile
from datetime import datetime
from xml.sax.saxutils import escape


def _xml_esc(val):
    if val is None:
        return ""
    return escape(str(val), {'"': "&quot;", "'": "&apos;"})


def _fmt_num(val, decimals=0):
    try:
        v = float(val or 0.0)
    except Exception:
        v = 0.0
    if decimals <= 0:
        return f"{int(round(v)):,}"
    return f"{v:,.{decimals}f}"


class OpenXmlSlideBuilder:
    """Builds a single PowerPoint slide XML (DrawingML) with native vector shapes,
    KPI cards, tables, column/bar charts, stacked charts, and pie/doughnut charts.
    Slide coordinate space: 16:9 widescreen (12,192,000 x 6,858,000 EMUs = 960 x 540 pt).
    1 pt = 12,700 EMUs.
    """

    PT = 12700
    WIDTH_PT = 960
    HEIGHT_PT = 540

    def __init__(self, slide_num, title="", subtitle="", period_label=""):
        self.slide_num = slide_num
        self.next_id = 2
        self.elements = []
        self.title = title
        self.subtitle = subtitle
        self.period_label = period_label

    def _id(self):
         cid = self.next_id
         self.next_id += 1
         return cid

    def _emu(self, pt):
        return int(round(float(pt) * self.PT))

    def add_rect(
        self, x, y, w, h, fill_hex="FFFFFF", line_hex=None, line_w_pt=1.0,
        round_radius=None, name="Rect"
    ):
        sid = self._id()
        X, Y, W, H = self._emu(x), self._emu(y), self._emu(w), self._emu(h)
        if round_radius is not None:
            prst = "roundRect"
            av = f'<a:avLst><a:gd name="adj" fmla="val {int(round_radius)}"/></a:avLst>'
        else:
            prst = "rect"
            av = "<a:avLst/>"

        fill_xml = f'<a:solidFill><a:srgbClr val="{fill_hex.lstrip("#").upper()}"/></a:solidFill>' if fill_hex else "<a:noFill/>"
        if line_hex:
            lw = max(int(round(line_w_pt * self.PT)), 6350)
            ln_xml = f'<a:ln w="{lw}"><a:solidFill><a:srgbClr val="{line_hex.lstrip("#").upper()}"/></a:solidFill></a:ln>'
        else:
            ln_xml = "<a:ln><a:noFill/></a:ln>"

        self.elements.append(
            f'<p:sp>'
            f'<p:nvSpPr><p:cNvPr id="{sid}" name="{_xml_esc(name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr>'
            f'<a:xfrm><a:off x="{X}" y="{Y}"/><a:ext cx="{W}" cy="{H}"/></a:xfrm>'
            f'<a:prstGeom prst="{prst}">{av}</a:prstGeom>'
            f'{fill_xml}{ln_xml}'
            f'</p:spPr>'
            f'</p:sp>'
        )

    def add_ellipse(self, x, y, w, h, fill_hex="FFFFFF", line_hex=None, line_w_pt=1.0, name="Oval"):
        sid = self._id()
        X, Y, W, H = self._emu(x), self._emu(y), self._emu(w), self._emu(h)
        fill_xml = f'<a:solidFill><a:srgbClr val="{fill_hex.lstrip("#").upper()}"/></a:solidFill>' if fill_hex else "<a:noFill/>"
        if line_hex:
            lw = max(int(round(line_w_pt * self.PT)), 6350)
            ln_xml = f'<a:ln w="{lw}"><a:solidFill><a:srgbClr val="{line_hex.lstrip("#").upper()}"/></a:solidFill></a:ln>'
        else:
            ln_xml = "<a:ln><a:noFill/></a:ln>"

        self.elements.append(
            f'<p:sp>'
            f'<p:nvSpPr><p:cNvPr id="{sid}" name="{_xml_esc(name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr>'
            f'<a:xfrm><a:off x="{X}" y="{Y}"/><a:ext cx="{W}" cy="{H}"/></a:xfrm>'
            f'<a:prstGeom prst="ellipse"><a:avLst/></a:prstGeom>'
            f'{fill_xml}{ln_xml}'
            f'</p:spPr>'
            f'</p:sp>'
        )

    def add_pie_slice(self, x, y, d, start_deg, end_deg, fill_hex, line_hex="FFFFFF", line_w_pt=1.2):
        sid = self._id()
        X, Y, D = self._emu(x), self._emu(y), self._emu(d)
        adj1 = max(0, min(21600000, int(round(start_deg * 60000))))
        adj2 = max(0, min(21600000, int(round(end_deg * 60000))))
        if adj2 - adj1 >= 21590000:
            self.add_ellipse(x, y, d, d, fill_hex=fill_hex, line_hex=line_hex, line_w_pt=line_w_pt)
            return
        if adj2 <= adj1:
            return
        lw = max(int(round(line_w_pt * self.PT)), 6350)
        self.elements.append(
            f'<p:sp>'
            f'<p:nvSpPr><p:cNvPr id="{sid}" name="PieSlice_{sid}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr>'
            f'<a:xfrm><a:off x="{X}" y="{Y}"/><a:ext cx="{D}" cy="{D}"/></a:xfrm>'
            f'<a:prstGeom prst="pie">'
            f'<a:avLst>'
            f'<a:gd name="adj1" fmla="val {adj1}"/>'
            f'<a:gd name="adj2" fmla="val {adj2}"/>'
            f'</a:avLst>'
            f'</a:prstGeom>'
            f'<a:solidFill><a:srgbClr val="{fill_hex.lstrip("#").upper()}"/></a:solidFill>'
            f'<a:ln w="{lw}"><a:solidFill><a:srgbClr val="{line_hex.lstrip("#").upper()}"/></a:solidFill></a:ln>'
            f'</p:spPr>'
            f'</p:sp>'
        )

    def add_text(
        self, x, y, w, h, text, size_pt=11, color_hex="0F172A", bold=False,
        italic=False, align="l", valign="t", fill_hex=None, line_hex=None,
        round_radius=None, pad_l=4, pad_r=4, pad_t=2, pad_b=2
    ):
        sid = self._id()
        X, Y, W, H = self._emu(x), self._emu(y), self._emu(w), self._emu(h)
        if round_radius is not None:
            prst = "roundRect"
            av = f'<a:avLst><a:gd name="adj" fmla="val {int(round_radius)}"/></a:avLst>'
        else:
            prst = "rect"
            av = "<a:avLst/>"

        fill_xml = f'<a:solidFill><a:srgbClr val="{fill_hex.lstrip("#").upper()}"/></a:solidFill>' if fill_hex else "<a:noFill/>"
        if line_hex:
            ln_xml = f'<a:ln w="12700"><a:solidFill><a:srgbClr val="{line_hex.lstrip("#").upper()}"/></a:solidFill></a:ln>'
        else:
            ln_xml = "<a:ln><a:noFill/></a:ln>"

        sz = int(round(size_pt * 100))
        b_attr = ' b="1"' if bold else ""
        i_attr = ' i="1"' if italic else ""
        c_hex = color_hex.lstrip("#").upper()

        lines = str(text or "").split("\n")
        paras = []
        for ln in lines:
            paras.append(
                f'<a:p>'
                f'<a:pPr algn="{align}"/>'
                f'<a:r>'
                f'<a:rPr lang="en-US" sz="{sz}"{b_attr}{i_attr} dirty="0">'
                f'<a:solidFill><a:srgbClr val="{c_hex}"/></a:solidFill>'
                f'<a:latin typeface="Segoe UI"/>'
                f'<a:ea typeface="Segoe UI"/>'
                f'<a:cs typeface="Segoe UI"/>'
                f'</a:rPr>'
                f'<a:t>{_xml_esc(ln)}</a:t>'
                f'</a:r>'
                f'</a:p>'
            )

        l_ins = self._emu(pad_l)
        r_ins = self._emu(pad_r)
        t_ins = self._emu(pad_t)
        b_ins = self._emu(pad_b)

        self.elements.append(
            f'<p:sp>'
            f'<p:nvSpPr><p:cNvPr id="{sid}" name="Text_{sid}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr>'
            f'<a:xfrm><a:off x="{X}" y="{Y}"/><a:ext cx="{W}" cy="{H}"/></a:xfrm>'
            f'<a:prstGeom prst="{prst}">{av}</a:prstGeom>'
            f'{fill_xml}{ln_xml}'
            f'</p:spPr>'
            f'<p:txBody>'
            f'<a:bodyPr wrap="square" lIns="{l_ins}" tIns="{t_ins}" rIns="{r_ins}" bIns="{b_ins}" anchor="{valign}"/>'
            f'<a:lstStyle/>'
            f'{"".join(paras)}'
            f'</p:txBody>'
            f'</p:sp>'
        )

    def add_header_chrome(self, badge_text, title, subtitle):
        # Clean light slide canvas background
        self.add_rect(0, 0, self.WIDTH_PT, self.HEIGHT_PT, fill_hex="F1F5F9")
        # Top dark navy executive header bar (#0F172A -> White text)
        self.add_rect(0, 0, self.WIDTH_PT, 56, fill_hex="0F172A")
        self.add_rect(0, 54, self.WIDTH_PT, 3, fill_hex="2563EB")

        # Slide pill badge
        self.add_text(
            24, 10, 150, 16, badge_text.upper(), size_pt=7.5, color_hex="FFFFFF",
            bold=True, align="c", valign="ctr", fill_hex="2563EB", round_radius=18000
        )
        # Main Title
        self.add_text(
            184, 6, 580, 26, title, size_pt=15.5, color_hex="FFFFFF", bold=True, align="l", valign="ctr"
        )
        # Subtitle
        self.add_text(
            184, 31, 620, 18, subtitle, size_pt=8.5, color_hex="CBD5E1", bold=False, align="l", valign="ctr"
        )
        # Right Period Badge
        if self.period_label:
            self.add_text(
                800, 13, 136, 28, self.period_label, size_pt=8.5, color_hex="FFFFFF",
                bold=True, align="c", valign="ctr", fill_hex="1E293B", line_hex="3B82F6", round_radius=12000
            )
        # Bottom Footer Bar
        self.add_rect(0, 520, self.WIDTH_PT, 20, fill_hex="0F172A")
        self.add_text(
            24, 521, 550, 16,
            "ANABTAWI GROUP  |  Executive HR & Payroll Intelligence Suite  |  Confidential Board Report",
            size_pt=7.0, color_hex="CBD5E1", align="l", valign="ctr"
        )
        self.add_text(
            820, 521, 116, 16,
            f"Slide {self.slide_num} of 10",
            size_pt=7.5, color_hex="FFFFFF", bold=True, align="r", valign="ctr"
        )

    def add_kpi_card(
        self, x, y, w, h, label, value_str, sub_str="", badge_str="",
        accent_hex="1E40AF", badge_bg="DBEAFE", badge_fg="1E3A8A", dark_header=True
    ):
        # Card container (White surface, crisp border)
        self.add_rect(x, y, w, h, fill_hex="FFFFFF", line_hex="CBD5E1", line_w_pt=1.0, round_radius=6000)
        if dark_header:
            self.add_rect(x, y, w, 22, fill_hex=accent_hex)
            self.add_text(x + 8, y + 2, w - 16, 18, label.upper(), size_pt=7.5, color_hex="FFFFFF", bold=True, valign="ctr")
            val_y = y + 26
        else:
            self.add_rect(x, y, 5, h, fill_hex=accent_hex)
            self.add_text(x + 10, y + 4, w - 16, 16, label.upper(), size_pt=7.5, color_hex="475569", bold=True, valign="ctr")
            val_y = y + 21

        self.add_text(x + 8, val_y, w - 16, 24, value_str, size_pt=15.0, color_hex="0F172A", bold=True, valign="ctr")
        if badge_str:
            self.add_text(
                x + 8, val_y + 25, min(w - 16, 115), 15, badge_str, size_pt=7.0,
                color_hex=badge_fg, bold=True, align="c", valign="ctr", fill_hex=badge_bg, round_radius=12000
            )
            if sub_str:
                self.add_text(x + 126, val_y + 24, max(w - 132, 30), 16, sub_str, size_pt=7.0, color_hex="334155", valign="ctr")
        elif sub_str:
            self.add_text(x + 8, val_y + 24, w - 16, 18, sub_str, size_pt=7.5, color_hex="334155", valign="ctr")

    def add_pie_donut_chart(
        self, x, y, w, h, title, subtitle, slices, center_top="", center_bottom="",
        header_hex="0F172A"
    ):
        """Draws a segmented card containing a native vector Doughnut/Pie chart
        with color-coded legend, exact values, and percentage shares.
        slices = [{"label": str, "value": float, "val_str": str, "color": hex}, ...]
        """
        self.add_rect(x, y, w, h, fill_hex="FFFFFF", line_hex="CBD5E1", round_radius=5000)
        self.add_rect(x, y, w, 24, fill_hex=header_hex)
        self.add_text(x + 10, y + 3, w - 20, 18, title, size_pt=8.5, color_hex="FFFFFF", bold=True, valign="ctr")
        if subtitle:
            self.add_text(x + 10, y + 25, w - 20, 14, subtitle, size_pt=7.0, color_hex="475569", valign="ctr")

        body_y = y + (40 if subtitle else 28)
        body_h = h - (body_y - y) - 8
        pie_d = min(body_h - 8, (w * 0.42))
        pie_x = x + 12
        pie_y = body_y + (body_h - pie_d) / 2.0

        valid_slices = [s for s in slices if float(s.get("value") or 0.0) > 0]
        total = sum(float(s.get("value") or 0.0) for s in valid_slices)

        if total <= 0:
            self.add_ellipse(pie_x, pie_y, pie_d, pie_d, fill_hex="E2E8F0", line_hex="CBD5E1")
        else:
            cur_deg = 0.0
            for idx, s in enumerate(valid_slices):
                val = float(s.get("value") or 0.0)
                sweep = (val / total) * 360.0
                end_deg = 360.0 if idx == len(valid_slices) - 1 else (cur_deg + sweep)
                if end_deg - cur_deg >= 0.4:
                    self.add_pie_slice(pie_x, pie_y, pie_d, cur_deg, end_deg, s.get("color", "2563EB"))
                cur_deg = end_deg

        # Inner Donut Hole (White surface + Dark bold text)
        hole_d = pie_d * 0.54
        hole_x = pie_x + (pie_d - hole_d) / 2.0
        hole_y = pie_y + (pie_d - hole_d) / 2.0
        self.add_ellipse(hole_x, hole_y, hole_d, hole_d, fill_hex="FFFFFF", line_hex="E2E8F0", line_w_pt=1.0)
        if center_top:
            self.add_text(
                hole_x + 2, hole_y + hole_d * 0.22, hole_d - 4, 16,
                center_top, size_pt=8.0, color_hex="0F172A", bold=True, align="c", valign="ctr"
            )
        if center_bottom:
            self.add_text(
                hole_x + 2, hole_y + hole_d * 0.52, hole_d - 4, 13,
                center_bottom, size_pt=6.5, color_hex="475569", bold=True, align="c", valign="ctr"
            )

        # Right-hand Legend & Data Breakdown
        leg_x = pie_x + pie_d + 12
        leg_w = (x + w) - leg_x - 8
        row_h = min(20.0, max(13.5, body_h / max(len(slices), 1)))
        for idx, s in enumerate(slices[:7]):
            ry = body_y + idx * row_h
            val = float(s.get("value") or 0.0)
            pct = (val / total * 100.0) if total > 0 else 0.0
            bg_row = "F8FAFC" if idx % 2 == 0 else "FFFFFF"
            self.add_rect(leg_x, ry, leg_w, row_h - 1.5, fill_hex=bg_row, line_hex="E2E8F0", line_w_pt=0.5)
            self.add_rect(leg_x + 3, ry + 3, 8, row_h - 7.5, fill_hex=s.get("color", "2563EB"))
            self.add_text(
                leg_x + 14, ry + 1, leg_w * 0.50, row_h - 3,
                s.get("label", ""), size_pt=7.0, color_hex="0F172A", bold=True, valign="ctr"
            )
            val_str = s.get("val_str") or _fmt_num(val, 0)
            self.add_text(
                leg_x + leg_w * 0.52, ry + 1, leg_w * 0.46, row_h - 3,
                f"{val_str} ({pct:.1f}%)", size_pt=7.0, color_hex="1E293B", bold=True, align="r", valign="ctr"
            )

    def add_grouped_column_chart(
        self, x, y, w, h, title, subtitle, categories, series_list,
        header_hex="0F172A", decimals=0, suffix=""
    ):
        """Draws a grouped vertical column chart with gridlines, legend, and value labels.
        series_list = [{"name": str, "values": [float, ...], "color": hex}, ...]
        """
        self.add_rect(x, y, w, h, fill_hex="FFFFFF", line_hex="CBD5E1", round_radius=5000)
        self.add_rect(x, y, w, 24, fill_hex=header_hex)
        self.add_text(x + 10, y + 3, w - 20, 18, title, size_pt=8.5, color_hex="FFFFFF", bold=True, valign="ctr")

        # Legend in top-right of chart body
        leg_y = y + 26
        if subtitle:
            self.add_text(x + 10, leg_y, w * 0.55, 14, subtitle, size_pt=7.0, color_hex="475569", valign="ctr")
        lx = x + w - 10
        for s in reversed(series_list):
            sname = s.get("name", "")
            lw = max(len(sname) * 4.5 + 18, 52)
            lx -= lw
            self.add_rect(lx, leg_y + 3, 9, 9, fill_hex=s.get("color", "2563EB"))
            self.add_text(lx + 11, leg_y + 1, lw - 12, 13, sname, size_pt=6.8, color_hex="0F172A", bold=True, valign="ctr")
            lx -= 6

        plot_x = x + 38
        plot_y = y + 46
        plot_w = w - 50
        plot_h = h - 72

        all_vals = [max(0.0, float(v or 0.0)) for s in series_list for v in s.get("values", [])]
        max_v = max(all_vals) if all_vals else 1.0
        if max_v <= 0:
            max_v = 1.0
        top_v = max_v * 1.18

        # Horizontal gridlines (4 steps)
        for g in range(5):
            gy = plot_y + plot_h - (plot_h * g / 4.0)
            gval = top_v * g / 4.0
            self.add_rect(plot_x, gy, plot_w, 0.6, fill_hex="CBD5E1" if g == 0 else "E2E8F0")
            lbl = _fmt_num(gval, 0) if gval >= 10 else _fmt_num(gval, decimals)
            self.add_text(x + 2, gy - 6, 34, 12, lbl, size_pt=6.2, color_hex="64748B", align="r", valign="ctr")

        n_cats = max(len(categories), 1)
        n_ser = max(len(series_list), 1)
        cat_w = plot_w / n_cats
        bar_group_w = cat_w * 0.68
        bar_w = bar_group_w / n_ser

        for c_idx, cat in enumerate(categories):
            group_x = plot_x + c_idx * cat_w + (cat_w - bar_group_w) / 2.0
            for s_idx, s in enumerate(series_list):
                vals = s.get("values", [])
                val = max(0.0, float(vals[c_idx] if c_idx < len(vals) else 0.0))
                bh = max(2.0, (val / top_v) * plot_h) if val > 0 else 1.5
                bx = group_x + s_idx * bar_w + 1.5
                by = plot_y + plot_h - bh
                self.add_rect(bx, by, max(bar_w - 3.0, 4.0), bh, fill_hex=s.get("color", "2563EB"))
                v_lbl = f"{_fmt_num(val, decimals)}{suffix}"
                self.add_text(
                    bx - 6, max(plot_y - 4, by - 13), max(bar_w + 12, 26), 12,
                    v_lbl, size_pt=6.5, color_hex="0F172A", bold=True, align="c", valign="ctr"
                )

            # X-axis category label
            self.add_text(
                plot_x + c_idx * cat_w, plot_y + plot_h + 3, cat_w, 16,
                str(cat), size_pt=7.2, color_hex="0F172A", bold=True, align="c", valign="ctr"
            )

    def add_stacked_column_chart(
        self, x, y, w, h, title, subtitle, categories, series_list,
        header_hex="0F172A", decimals=0
    ):
        """Draws a 3-month or multi-category stacked column chart (e.g. Underlying Cost + EOS)."""
        self.add_rect(x, y, w, h, fill_hex="FFFFFF", line_hex="CBD5E1", round_radius=5000)
        self.add_rect(x, y, w, 24, fill_hex=header_hex)
        self.add_text(x + 10, y + 3, w - 20, 18, title, size_pt=8.5, color_hex="FFFFFF", bold=True, valign="ctr")

        leg_y = y + 26
        if subtitle:
            self.add_text(x + 10, leg_y, w * 0.52, 14, subtitle, size_pt=7.0, color_hex="475569", valign="ctr")
        lx = x + w - 10
        for s in reversed(series_list):
            sname = s.get("name", "")
            lw = max(len(sname) * 4.5 + 18, 55)
            lx -= lw
            self.add_rect(lx, leg_y + 3, 9, 9, fill_hex=s.get("color", "2563EB"))
            self.add_text(lx + 11, leg_y + 1, lw - 12, 13, sname, size_pt=6.8, color_hex="0F172A", bold=True, valign="ctr")
            lx -= 6

        plot_x = x + 42
        plot_y = y + 46
        plot_w = w - 54
        plot_h = h - 72

        n_cats = max(len(categories), 1)
        totals = []
        for c_idx in range(n_cats):
            t = sum(max(0.0, float((s.get("values") or [0])[c_idx] if c_idx < len(s.get("values", [])) else 0.0)) for s in series_list)
            totals.append(t)
        max_v = max(totals) if totals and max(totals) > 0 else 1.0
        top_v = max_v * 1.18

        for g in range(5):
            gy = plot_y + plot_h - (plot_h * g / 4.0)
            gval = top_v * g / 4.0
            self.add_rect(plot_x, gy, plot_w, 0.6, fill_hex="CBD5E1" if g == 0 else "E2E8F0")
            self.add_text(x + 2, gy - 6, 38, 12, _fmt_num(gval, 0), size_pt=6.2, color_hex="64748B", align="r", valign="ctr")

        cat_w = plot_w / n_cats
        bar_w = min(cat_w * 0.52, 58.0)

        for c_idx, cat in enumerate(categories):
            bx = plot_x + c_idx * cat_w + (cat_w - bar_w) / 2.0
            cur_bottom = plot_y + plot_h
            for s in series_list:
                vals = s.get("values", [])
                val = max(0.0, float(vals[c_idx] if c_idx < len(vals) else 0.0))
                if val <= 0:
                    continue
                bh = max(2.0, (val / top_v) * plot_h)
                by = cur_bottom - bh
                self.add_rect(bx, by, bar_w, bh, fill_hex=s.get("color", "2563EB"), line_hex="FFFFFF", line_w_pt=0.5)
                if bh >= 14:
                    self.add_text(bx, by + (bh - 11) / 2.0, bar_w, 11, _fmt_num(val, decimals), size_pt=6.3, color_hex="FFFFFF", bold=True, align="c", valign="ctr")
                cur_bottom = by

            # Total label above stack
            tot_val = totals[c_idx]
            self.add_text(
                bx - 12, max(plot_y - 4, cur_bottom - 13), bar_w + 24, 12,
                _fmt_num(tot_val, decimals), size_pt=6.8, color_hex="0F172A", bold=True, align="c", valign="ctr"
            )
            self.add_text(
                plot_x + c_idx * cat_w, plot_y + plot_h + 3, cat_w, 16,
                str(cat), size_pt=7.2, color_hex="0F172A", bold=True, align="c", valign="ctr"
            )

    def add_horizontal_bar_chart(
        self, x, y, w, h, title, subtitle, items, header_hex="0F172A", suffix="%"
    ):
        """Draws a horizontal ranking bar chart.
        items = [{"label": str, "value": float, "color": hex, "tag": str}, ...]
        """
        self.add_rect(x, y, w, h, fill_hex="FFFFFF", line_hex="CBD5E1", round_radius=5000)
        self.add_rect(x, y, w, 24, fill_hex=header_hex)
        self.add_text(x + 10, y + 3, w - 20, 18, title, size_pt=8.5, color_hex="FFFFFF", bold=True, valign="ctr")
        if subtitle:
            self.add_text(x + 10, y + 25, w - 20, 14, subtitle, size_pt=7.0, color_hex="475569", valign="ctr")

        body_y = y + (41 if subtitle else 28)
        body_h = h - (body_y - y) - 8
        n = max(len(items), 1)
        row_h = min(26.0, body_h / n)
        max_v = max([float(i.get("value") or 0.0) for i in items] + [1.0])
        top_v = max_v * 1.22 if max_v > 0 else 1.0

        lbl_w = w * 0.34
        bar_area_x = x + lbl_w + 8
        bar_area_w = w - lbl_w - 64

        for idx, it in enumerate(items):
            ry = body_y + idx * row_h
            val = max(0.0, float(it.get("value") or 0.0))
            bw = max(3.0, (val / top_v) * bar_area_w) if val > 0 else 2.0
            self.add_text(x + 8, ry + 2, lbl_w - 4, row_h - 4, it.get("label", ""), size_pt=7.2, color_hex="0F172A", bold=True, align="r", valign="ctr")
            self.add_rect(bar_area_x, ry + 4, bar_area_w, row_h - 8, fill_hex="F1F5F9")
            self.add_rect(bar_area_x, ry + 4, bw, row_h - 8, fill_hex=it.get("color", "2563EB"))
            val_txt = it.get("val_str") or f"{val:.1f}{suffix}"
            self.add_text(bar_area_x + bw + 4, ry + 2, 52, row_h - 4, val_txt, size_pt=7.2, color_hex="0F172A", bold=True, valign="ctr")

    def add_table_grid(
        self, x, y, w, col_widths, headers, rows, row_h=18.5, header_h=22.0,
        header_bg="0F172A", total_row_indices=None, font_size=7.2, header_font_size=7.4
    ):
        """Renders a crisp, high-contrast data table using vector cells so every cell's
        background, border, alignment, and text contrast are guaranteed across all viewers."""
        total_set = set(total_row_indices or [])
        total_w = sum(col_widths) or 1.0
        scaled_widths = [w * (cw / total_w) for cw in col_widths]

        # Header Row (Dark background #0F172A -> Crisp White Text #FFFFFF)
        cx = x
        for c_idx, h_text in enumerate(headers):
            cw = scaled_widths[c_idx]
            align = "l" if c_idx == 0 else "c"
            self.add_rect(cx, y, cw, header_h, fill_hex=header_bg, line_hex="334155", line_w_pt=0.6)
            self.add_text(
                cx + 3, y + 1, cw - 6, header_h - 2, h_text,
                size_pt=header_font_size, color_hex="FFFFFF", bold=True, align=align, valign="ctr"
            )
            cx += cw

        cur_y = y + header_h
        for r_idx, row in enumerate(rows):
            is_tot = r_idx in total_set
            default_bg = "0F172A" if is_tot else ("FFFFFF" if r_idx % 2 == 0 else "F8FAFC")
            default_fg = "FFFFFF" if is_tot else "0F172A"
            cx = x
            for c_idx, cell in enumerate(row):
                cw = scaled_widths[c_idx]
                if isinstance(cell, dict):
                    txt = str(cell.get("text", ""))
                    bg = cell.get("bg", default_bg)
                    fg = cell.get("fg", default_fg)
                    bld = cell.get("bold", is_tot or c_idx == 0)
                    algn = cell.get("align", "l" if c_idx == 0 else "r")
                else:
                    txt = str(cell)
                    bg = default_bg
                    fg = default_fg
                    bld = is_tot or c_idx == 0
                    algn = "l" if c_idx == 0 else "r"

                self.add_rect(cx, cur_y, cw, row_h, fill_hex=bg, line_hex="CBD5E1", line_w_pt=0.5)
                self.add_text(
                    cx + 3, cur_y + 1, cw - 6, row_h - 2, txt,
                    size_pt=font_size, color_hex=fg, bold=bld, align=algn, valign="ctr"
                )
                cx += cw
            cur_y += row_h

    def to_xml(self):
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:cSld name="Slide ' + str(self.slide_num) + '">'
            '<p:spTree>'
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            + "".join(self.elements) +
            '</p:spTree>'
            '</p:cSld>'
            '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>'
            '</p:sld>'
        )


def build_board_pptx_bytes(data):
    """Generates a complete 10-Slide Executive Board PowerPoint (.pptx) binary stream
    from `hr.payroll.dashboard.get_dashboard_data()` payload."""
    kpis = data.get("kpis") or {}
    cb = data.get("cost_bridge") or {}
    lcr = data.get("labor_cost_report") or []
    lct = data.get("labor_cost_totals") or {}
    tmt = data.get("three_month_trend") or {}
    wm = data.get("workforce_movement") or {}
    ins = data.get("executive_insights") or {}

    m0_lbl = tmt.get("m2_label") or "Month - 2"
    m1_lbl = tmt.get("m1_label") or "Month - 1"
    m2_lbl = tmt.get("m0_label") or "Current"
    period_title = m2_lbl
    selected_comp_name = data.get("selected_company_name") or "All Companies (جميع الشركات)"

    s3m = tmt.get("series_3m") or {}

    def _s3(key, fallback_curr=0.0):
        arr = s3m.get(key)
        if isinstance(arr, list) and len(arr) >= 3:
            return [float(arr[0] or 0.0), float(arr[1] or 0.0), float(arr[2] or 0.0)]
        return [float(fallback_curr or 0.0)] * 3

    end_hc = int(lct.get("ending_hc") or kpis.get("headcount") or 0)
    beg_hc = int(lct.get("beginning_hc") or end_hc)
    new_hires = int(lct.get("new_hires") or 0)
    separations = int(lct.get("separations") or 0)
    net_hc_diff = end_hc - beg_hc

    rep_cost = float(cb.get("reported_workforce_cost") or lct.get("total_workforce_cost") or 0.0)
    eos_cost = float(cb.get("eos_settlement_cost") or lct.get("eos_amount") or 0.0)
    und_cost = float(cb.get("underlying_workforce_cost") or (rep_cost - eos_cost) or 0.0)
    und_avg = float(cb.get("underlying_avg_cost_per_emp") or lct.get("underlying_avg_cost_per_emp") or 0.0)
    rep_avg = float(cb.get("reported_avg_cost_per_emp") or (rep_cost / end_hc if end_hc else 0.0))
    ot_cost = float(lct.get("overtime_amount") or kpis.get("overtime_amount") or 0.0)
    ot_pct = float(lct.get("overtime_cost_pct") or 0.0)
    turnover_rate = float(wm.get("turnover_rate") or lct.get("turnover_rate") or 0.0)
    vol_pct = float(wm.get("voluntary_share_pct") or lct.get("voluntary_share_pct") or 0.0)

    beg_hc_3m = _s3("beg_hc", beg_hc)
    hires_3m = _s3("hires", new_hires)
    seps_3m = _s3("seps", separations)
    end_hc_3m = _s3("end_hc", end_hc)
    rep_cost_3m = _s3("rep_cost", rep_cost)
    eos_cost_3m = _s3("eos_cost", eos_cost)
    und_cost_3m = _s3("und_cost", und_cost)
    rep_avg_3m = _s3("rep_avg", rep_avg)
    und_avg_3m = _s3("und_avg", und_avg)
    ot_cost_3m = _s3("ot_cost", ot_cost)
    ot_pct_3m = _s3("ot_pct", ot_pct)

    rep_mom_pct = ((rep_cost_3m[2] - rep_cost_3m[1]) / rep_cost_3m[1] * 100.0) if rep_cost_3m[1] > 0 else 0.0
    und_mom_pct = ((und_cost_3m[2] - und_cost_3m[1]) / und_cost_3m[1] * 100.0) if und_cost_3m[1] > 0 else 0.0
    eos_share_pct = float(cb.get("eos_pct_of_reported") or ((eos_cost / rep_cost * 100.0) if rep_cost > 0 else 0.0))

    slides = []

    # =========================================================================
    # SLIDE 1: EXECUTIVE COVER SLIDE
    # =========================================================================
    s1 = OpenXmlSlideBuilder(1, period_label=period_title)
    s1.add_rect(0, 0, 960, 540, fill_hex="0F172A")
    s1.add_rect(0, 0, 960, 8, fill_hex="2563EB")
    s1.add_rect(48, 48, 864, 315, fill_hex="1E293B", line_hex="334155", line_w_pt=1.2, round_radius=6000)
    s1.add_text(
        76, 72, 260, 24, "ANABTAWI GROUP  |  BOARD BRIEFING",
        size_pt=9.0, color_hex="FFFFFF", bold=True, align="c", valign="ctr",
        fill_hex="2563EB", round_radius=15000
    )
    s1.add_text(
        76, 112, 800, 54, f"HR & Payroll Executive Dashboard — {period_title}",
        size_pt=28.0, color_hex="FFFFFF", bold=True, valign="ctr"
    )
    s1.add_text(
        76, 170, 800, 32,
        "Corporate Workforce Cost Bridge, Headcount Movement, Overtime Efficiency & Turnover Risk Intelligence",
        size_pt=13.0, color_hex="93C5FD", bold=True, valign="ctr"
    )
    s1.add_rect(76, 214, 780, 1.5, fill_hex="334155")
    s1.add_text(
        76, 226, 780, 26,
        f"Company Scope: {selected_comp_name}   |   3-Month Window ({m0_lbl} – {m2_lbl})   |   Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        size_pt=9.8, color_hex="E2E8F0", bold=True, valign="ctr"
    )
    # 3 Scope Pills inside hero box
    s1.add_text(76, 268, 245, 34, f"1. 3-Month Trend ({m0_lbl} – {m2_lbl})", size_pt=9.5, color_hex="FFFFFF", bold=True, align="c", valign="ctr", fill_hex="0F172A", line_hex="3B82F6", round_radius=12000)
    s1.add_text(336, 268, 265, 34, f"2. {period_title} SBU Labor Cost Matrix", size_pt=9.5, color_hex="FFFFFF", bold=True, align="c", valign="ctr", fill_hex="0F172A", line_hex="10B981", round_radius=12000)
    s1.add_text(616, 268, 255, 34, "3. Turnover & Retention Deep-Dive", size_pt=9.5, color_hex="FFFFFF", bold=True, align="c", valign="ctr", fill_hex="0F172A", line_hex="F59E0B", round_radius=12000)

    # 4 Bottom Live KPI Cards on Cover
    s1.add_kpi_card(48, 384, 204, 108, "Ending Headcount", f"{end_hc:,} Emp", f"Beg: {beg_hc} | +{new_hires} / -{separations}", f"Net: {net_hc_diff:+d}", accent_hex="2563EB")
    s1.add_kpi_card(268, 384, 204, 108, "Reported Workforce Cost", f"{_fmt_num(rep_cost, 0)} JOD", f"Avg: {_fmt_num(rep_avg, 0)} JOD/Emp", f"MoM: {rep_mom_pct:+.1f}%", accent_hex="0D9488")
    s1.add_kpi_card(488, 384, 204, 108, "Underlying Cost (Excl. EOS)", f"{_fmt_num(und_cost, 0)} JOD", f"EOS Isolated: {_fmt_num(eos_cost, 0)} JOD", f"MoM: {und_mom_pct:+.1f}%", accent_hex="4F46E5")
    s1.add_kpi_card(708, 384, 204, 108, "Overtime & Turnover", f"OT: {ot_pct:.2f}%", f"OT: {_fmt_num(ot_cost, 0)} JOD", f"Turnover: {turnover_rate:.1f}%", accent_hex="D97706")
    slides.append(s1.to_xml())

    # =========================================================================
    # SLIDE 2: EXECUTIVE SUMMARY (KPIs + COST PIE CHART + BOARD NARRATIVE)
    # =========================================================================
    s2 = OpenXmlSlideBuilder(2, period_label=period_title)
    s2.add_header_chrome(
        "EXECUTIVE SUMMARY",
        f"Executive Summary — {period_title} Key Workforce Metrics",
        "Headline KPIs, corporate cost structure doughnut chart, and automated board narrative"
    )
    s2.add_kpi_card(24, 66, 218, 92, "Ending Headcount", f"{end_hc:,} Employees", f"+{new_hires} Hires / -{separations} Exits", f"Net {net_hc_diff:+d} MoM", accent_hex="1E40AF")
    s2.add_kpi_card(255, 66, 218, 92, "Total Workforce Cost", f"{_fmt_num(rep_cost, 0)} JOD", f"Avg {_fmt_num(rep_avg, 0)} JOD / Emp", f"{rep_mom_pct:+.1f}% MoM", accent_hex="0F766E")
    s2.add_kpi_card(486, 66, 218, 92, "Underlying Cost (Excl. EOS)", f"{_fmt_num(und_cost, 0)} JOD", f"Excl. {_fmt_num(eos_cost, 0)} JOD EOS", f"Avg {_fmt_num(und_avg, 0)} JOD", accent_hex="4338CA")
    s2.add_kpi_card(717, 66, 219, 92, "Overtime Cost & Share", f"{_fmt_num(ot_cost, 0)} JOD", f"Share of Cost: {ot_pct:.2f}%", f"Turnover: {turnover_rate:.1f}%", accent_hex="B45309")

    # Left: Workforce Cost Structure Pie/Doughnut Chart
    cost_slices = [
        {"label": "Basic Salaries", "value": float(lct.get("basic_salary") or 0.0), "color": "1E3A8A"},
        {"label": "Allowances", "value": float(lct.get("allowances") or 0.0), "color": "2563EB"},
        {"label": "Social Security (14.25%)", "value": float(lct.get("social_security_comp") or 0.0), "color": "7C3AED"},
        {"label": "Overtime Pay", "value": float(lct.get("overtime_amount") or 0.0), "color": "D97706"},
        {"label": "Health Insurance (Co.)", "value": float(lct.get("health_ins_comp") or 0.0), "color": "0891B2"},
        {"label": "End of Service (EOS)", "value": float(lct.get("eos_amount") or 0.0), "color": "DC2626"},
    ]
    s2.add_pie_donut_chart(
        24, 168, 448, 340,
        f"Corporate Workforce Cost Structure — {period_title}",
        "Distribution of total company payroll cost across statutory & operating components",
        cost_slices,
        center_top=f"{_fmt_num(rep_cost, 0)}",
        center_bottom="Total JOD",
        header_hex="0F172A"
    )

    # Right: 3 Executive Narrative Pillar Cards
    bullets = [
        f"Active workforce moved from {beg_hc} to {end_hc} employees in {period_title} (+{new_hires} new hires vs. -{separations} separations; net movement {net_hc_diff:+d}).",
        f"Reported workforce cost totaled {_fmt_num(rep_cost, 0)} JOD ({rep_mom_pct:+.1f}% MoM). Isolating {_fmt_num(eos_cost, 0)} JOD in EOS settlements yields an underlying operating cost of {_fmt_num(und_cost, 0)} JOD ({_fmt_num(und_avg, 0)} JOD/employee).",
        f"Overtime spend reached {_fmt_num(ot_cost, 0)} JOD ({ot_pct:.2f}% of total workforce cost), while monthly turnover registered {turnover_rate:.1f}% ({vol_pct:.0f}% voluntary resignations)."
    ]
    card_configs = [
        ("1. WORKFORCE & HEADCOUNT TRAJECTORY", "1E40AF", bullets[0]),
        ("2. HEADLINE VS. UNDERLYING COST (EOS ISOLATION)", "0F766E", bullets[1]),
        ("3. OVERTIME EFFICIENCY & RETENTION FOCUS", "B45309", bullets[2]),
    ]
    for idx, (ctitle, ccolor, cbody) in enumerate(card_configs):
        cy = 168 + idx * 116
        s2.add_rect(486, cy, 450, 108, fill_hex="FFFFFF", line_hex="CBD5E1", round_radius=5000)
        s2.add_rect(486, cy, 450, 24, fill_hex=ccolor)
        s2.add_text(496, cy + 3, 430, 18, ctitle, size_pt=8.5, color_hex="FFFFFF", bold=True, valign="ctr")
        s2.add_text(496, cy + 28, 430, 74, cbody, size_pt=9.0, color_hex="0F172A", valign="ctr")
    slides.append(s2.to_xml())

    # =========================================================================
    # SLIDE 3: 3-MONTH HEADCOUNT TREND (M-2 TO CURRENT)
    # =========================================================================
    s3 = OpenXmlSlideBuilder(3, period_label=f"{m0_lbl} – {m2_lbl}")
    s3.add_header_chrome(
        "HEADCOUNT TREND",
        f"3-Month Headcount Bridge & Hiring Velocity ({m0_lbl} – {m2_lbl})",
        "Comparison of Beginning vs. Ending Headcount and Gross Additions vs. Separations"
    )
    s3.add_grouped_column_chart(
        24, 68, 610, 214,
        "Beginning vs. Ending Headcount (3-Month Trajectory)",
        "Active employees at start vs. end of each payroll period",
        [m0_lbl, m1_lbl, m2_lbl],
        [
            {"name": "Beginning HC", "values": beg_hc_3m, "color": "64748B"},
            {"name": "Ending HC", "values": end_hc_3m, "color": "1E40AF"},
        ],
        header_hex="0F172A",
        decimals=0
    )
    s3.add_grouped_column_chart(
        24, 292, 610, 216,
        "Monthly New Hires (+) vs. Separations (-) Across 3 Months",
        "Gross workforce additions compared against monthly employee exits",
        [m0_lbl, m1_lbl, m2_lbl],
        [
            {"name": "New Hires (+)", "values": hires_3m, "color": "059669"},
            {"name": "Separations (-)", "values": seps_3m, "color": "DC2626"},
        ],
        header_hex="1E3A8A",
        decimals=0
    )

    net_3m = int(end_hc_3m[2] - beg_hc_3m[0]) if len(end_hc_3m) == 3 and len(beg_hc_3m) == 3 else net_hc_diff
    tot_hires_3m = int(sum(hires_3m))
    tot_seps_3m = int(sum(seps_3m))
    repl_ratio = (tot_hires_3m / tot_seps_3m) if tot_seps_3m > 0 else float(tot_hires_3m or 1.0)

    s3.add_kpi_card(648, 68, 288, 102, "3-Month Net Headcount Change", f"{net_3m:+d} Employees", f"From {int(beg_hc_3m[0])} ({m0_lbl}) to {int(end_hc_3m[2])} ({m2_lbl})", "3-Month Net Bridge", accent_hex="1E40AF")
    s3.add_kpi_card(648, 180, 288, 102, "3-Month Gross Additions", f"+{tot_hires_3m:,} New Hires", f"Current Month ({m2_lbl}): +{new_hires} Hires", "Gross Onboarding", accent_hex="059669")
    s3.add_kpi_card(648, 292, 288, 102, "3-Month Gross Separations", f"-{tot_seps_3m:,} Exits", f"Current Month ({m2_lbl}): -{separations} Exits", f"Turnover: {turnover_rate:.1f}%", accent_hex="DC2626")
    s3.add_kpi_card(648, 404, 288, 104, "Replacement Velocity Ratio", f"{repl_ratio:.2f}x", "Hires per Separation (>1.0x = Net Expansion)", "Workforce Stability", accent_hex="4F46E5")
    slides.append(s3.to_xml())

    # =========================================================================
    # SLIDE 4: HEADLINE VS. UNDERLYING WORKFORCE COST (ISOLATING EOS)
    # =========================================================================
    s4 = OpenXmlSlideBuilder(4, period_label=period_title)
    s4.add_header_chrome(
        "COST BRIDGE & EOS",
        "Headline vs. Underlying Workforce Cost — Isolating End-of-Service (EOS)",
        "Separating one-off termination settlements from recurring monthly operating payroll"
    )
    # Top 3-Step Cost Bridge Banner
    s4.add_kpi_card(24, 66, 292, 88, "1. Reported Workforce Cost (Incl. EOS)", f"{_fmt_num(rep_cost, 0)} JOD", f"Reported Avg: {_fmt_num(rep_avg, 0)} JOD/Emp", f"MoM: {rep_mom_pct:+.1f}%", accent_hex="0F172A")
    s4.add_kpi_card(334, 66, 292, 88, "2. Less: End-of-Service (EOS Settlements)", f"- {_fmt_num(eos_cost, 0)} JOD", f"{eos_share_pct:.1f}% of Total Payroll Cost", "One-Off Settlements", accent_hex="DC2626", badge_bg="FEE2E2", badge_fg="991B1B")
    s4.add_kpi_card(644, 66, 292, 88, "3. Equals: Underlying Operating Cost", f"{_fmt_num(und_cost, 0)} JOD", f"True Avg: {_fmt_num(und_avg, 0)} JOD/Emp", f"MoM: {und_mom_pct:+.1f}%", accent_hex="059669", badge_bg="D1FAE5", badge_fg="065F46")

    # Stacked Column Chart: Underlying Cost + EOS across 3 months
    s4.add_stacked_column_chart(
        24, 164, 448, 344,
        f"3-Month Workforce Cost Decomposition ({m0_lbl} – {m2_lbl})",
        "Stacked comparison of Underlying Operating Cost vs. EOS Settlements (JOD)",
        [m0_lbl, m1_lbl, m2_lbl],
        [
            {"name": "Underlying Cost (Excl. EOS)", "values": und_cost_3m, "color": "1E40AF"},
            {"name": "End-of-Service (EOS)", "values": eos_cost_3m, "color": "DC2626"},
        ],
        header_hex="0F172A",
        decimals=0
    )
    # Grouped Column Chart: Reported Avg Cost/Emp vs Underlying Avg Cost/Emp
    s4.add_grouped_column_chart(
        486, 164, 450, 344,
        "Average Cost per Employee: Reported vs. Underlying (Excl. EOS)",
        "Demonstrates how one-off EOS payouts skew headline per-employee cost (JOD)",
        [m0_lbl, m1_lbl, m2_lbl],
        [
            {"name": "Reported Avg/Emp", "values": rep_avg_3m, "color": "D97706"},
            {"name": "Underlying Avg/Emp (Excl. EOS)", "values": und_avg_3m, "color": "059669"},
        ],
        header_hex="0F766E",
        decimals=0
    )
    slides.append(s4.to_xml())

    # =========================================================================
    # SLIDE 5: OVERTIME ANALYSIS (3-MONTH TREND, PIE CHART & SBU TABLE)
    # =========================================================================
    s5 = OpenXmlSlideBuilder(5, period_label=period_title)
    s5.add_header_chrome(
        "OVERTIME ANALYTICS",
        f"Overtime Trend & Business Unit Concentration — {period_title}",
        "3-month overtime trajectory, Business Unit share pie chart, and SBU intensity matrix"
    )
    s5.add_grouped_column_chart(
        24, 66, 448, 212,
        f"3-Month Overtime Cost Trend ({m0_lbl} – {m2_lbl})",
        "Monthly overtime expenditure in JOD across the 3-month window",
        [m0_lbl, m1_lbl, m2_lbl],
        [
            {"name": "Overtime Cost (JOD)", "values": ot_cost_3m, "color": "D97706"},
        ],
        header_hex="B45309",
        decimals=0
    )

    sbu_colors = ["1E3A8A", "2563EB", "7C3AED", "0D9488", "D97706"]
    ot_slices = []
    for idx, r in enumerate(lcr):
        ot_slices.append({
            "label": r.get("sbu_name_en") or r.get("sbu_display_name"),
            "value": float(r.get("overtime_amount") or 0.0),
            "color": sbu_colors[idx % len(sbu_colors)],
        })
    s5.add_pie_donut_chart(
        24, 286, 448, 222,
        f"Overtime Share by Business Unit — {period_title}",
        "Distribution of total overtime spend across Strategic Business Units",
        ot_slices,
        center_top=f"{_fmt_num(ot_cost, 0)}",
        center_bottom="OT JOD",
        header_hex="0F172A"
    )

    # Right: SBU Overtime Breakdown Table
    s5.add_rect(486, 66, 450, 442, fill_hex="FFFFFF", line_hex="CBD5E1", round_radius=5000)
    s5.add_rect(486, 66, 450, 24, fill_hex="0F172A")
    s5.add_text(496, 69, 430, 18, f"Business Unit Overtime Breakdown — {period_title}", size_pt=8.5, color_hex="FFFFFF", bold=True, valign="ctr")

    ot_headers = ["Business Unit", "End HC", "OT Cost (JOD)", "Share of OT", "OT % of BU Cost", "Status"]
    ot_rows = []
    for r in lcr:
        bu_ot = float(r.get("overtime_amount") or 0.0)
        bu_ot_share = (bu_ot / ot_cost * 100.0) if ot_cost > 0 else 0.0
        bu_ot_pct = float(r.get("overtime_cost_pct") or 0.0)
        status_cell = (
            {"text": "HIGH (>3%)", "bg": "FEE2E2", "fg": "991B1B", "bold": True, "align": "c"}
            if bu_ot_pct > 3.0 else
            ({"text": "WATCH", "bg": "FEF3C7", "fg": "92400E", "bold": True, "align": "c"}
             if bu_ot_pct > 1.8 else
             {"text": "NORMAL", "bg": "D1FAE5", "fg": "065F46", "bold": True, "align": "c"})
        )
        ot_rows.append([
            r.get("sbu_name_en") or r.get("sbu_display_name"),
            str(r.get("ending_hc") or 0),
            _fmt_num(bu_ot, 0),
            f"{bu_ot_share:.1f}%",
            f"{bu_ot_pct:.2f}%",
            status_cell,
        ])
    ot_rows.append([
        "TOTAL GROUP",
        str(end_hc),
        _fmt_num(ot_cost, 0),
        "100.0%",
        f"{ot_pct:.2f}%",
        {"text": f"{ot_pct:.2f}%", "bg": "0F172A", "fg": "FFFFFF", "bold": True, "align": "c"},
    ])
    s5.add_table_grid(
        494, 98, 434, [130, 48, 72, 62, 66, 56],
        ot_headers, ot_rows, row_h=24.0, header_h=24.0, total_row_indices=[len(ot_rows) - 1]
    )

    # Operational OT Takeaway Box
    top_ot_bu = max(lcr, key=lambda x: float(x.get("overtime_amount") or 0.0)) if lcr else {}
    s5.add_rect(494, 286, 434, 210, fill_hex="FFFBEB", line_hex="F59E0B", round_radius=5000)
    s5.add_rect(494, 286, 434, 24, fill_hex="B45309")
    s5.add_text(504, 289, 414, 18, "KEY OVERTIME DRIVERS & ACTION GUIDELINES", size_pt=8.2, color_hex="FFFFFF", bold=True, valign="ctr")
    ot_notes = (
        f"• Primary OT Driver: {top_ot_bu.get('sbu_name_en', 'N/A')} recorded {_fmt_num(top_ot_bu.get('overtime_amount', 0), 0)} JOD "
        f"({top_ot_bu.get('overtime_cost_pct', 0):.2f}% of its workforce cost).\n\n"
        f"• 3-Month Trend: Group overtime moved from {_fmt_num(ot_cost_3m[0], 0)} JOD ({ot_pct_3m[0]:.2f}%) in {m0_lbl} "
        f"to {_fmt_num(ot_cost_3m[1], 0)} JOD ({ot_pct_3m[1]:.2f}%) in {m1_lbl} and {_fmt_num(ot_cost_3m[2], 0)} JOD ({ot_pct_3m[2]:.2f}%) in {m2_lbl}.\n\n"
        f"• Governance Target: Keep Business Unit overtime below 3.0% of total unit payroll by aligning shift rosters with new-hire onboarding."
    )
    s5.add_text(504, 316, 414, 170, ot_notes, size_pt=8.5, color_hex="0F172A", valign="t")
    slides.append(s5.to_xml())

    # =========================================================================
    # SLIDE 6: 3-MONTH SUMMARY TABLE & BOARD EVALUATION
    # =========================================================================
    s6 = OpenXmlSlideBuilder(6, period_label=f"{m0_lbl} – {m2_lbl}")
    s6.add_header_chrome(
        "3-MONTH BOARD TABLE",
        f"3-Month Summary Comparison Table & Board Conclusion ({m0_lbl} – {m2_lbl})",
        "Comprehensive side-by-side performance across all 12 Board KPIs with RAG status"
    )
    t6_headers = ["Board KPI / Workforce Metric", m0_lbl, m1_lbl, m2_lbl, "MoM Change", "Status"]
    t6_rows = []
    for r in (tmt.get("rows") or []):
        rag = r.get("rag") or "green"
        rag_cell = (
            {"text": "WATCH", "bg": "FEE2E2", "fg": "991B1B", "bold": True, "align": "c"}
            if rag == "red" else
            ({"text": "MODERATE", "bg": "FEF3C7", "fg": "92400E", "bold": True, "align": "c"}
             if rag == "amber" else
             {"text": "FAVORABLE", "bg": "D1FAE5", "fg": "065F46", "bold": True, "align": "c"})
        )
        t6_rows.append([
            r.get("kpi", ""),
            str(r.get("m2", "")),
            str(r.get("m1", "")),
            {"text": str(r.get("m0", "")), "bg": "EFF6FF", "fg": "1E3A8A", "bold": True, "align": "r"},
            {"text": str(r.get("mom", "")), "bg": "F8FAFC", "fg": "0F172A", "bold": True, "align": "c"},
            rag_cell,
        ])
    s6.add_table_grid(
        24, 66, 610, [215, 82, 82, 88, 75, 68],
        t6_headers, t6_rows, row_h=34.0, header_h=26.0, font_size=7.1
    )

    # Right Side: Positives (Green) & Attention Points (Red)
    positives = ins.get("positives") or ["Controlled underlying operating cost per employee."]
    attentions = ins.get("attention_points") or ["Monitor monthly separations and overtime in operational units."]

    s6.add_rect(648, 66, 288, 214, fill_hex="FFFFFF", line_hex="10B981", round_radius=5000)
    s6.add_rect(648, 66, 288, 26, fill_hex="059669")
    s6.add_text(658, 69, 268, 20, "POSITIVES & FAVORABLE TRENDS", size_pt=8.5, color_hex="FFFFFF", bold=True, valign="ctr")
    pos_txt = "\n\n".join(f"✓  {p}" for p in positives[:4])
    s6.add_text(658, 98, 268, 174, pos_txt, size_pt=8.2, color_hex="0F172A", valign="t")

    s6.add_rect(648, 292, 288, 216, fill_hex="FFFFFF", line_hex="EF4444", round_radius=5000)
    s6.add_rect(648, 292, 288, 26, fill_hex="DC2626")
    s6.add_text(658, 295, 268, 20, "ATTENTION POINTS & RISK WATCH", size_pt=8.5, color_hex="FFFFFF", bold=True, valign="ctr")
    att_txt = "\n\n".join(f"▲  {a}" for a in attentions[:4])
    s6.add_text(658, 324, 268, 176, att_txt, size_pt=8.2, color_hex="0F172A", valign="t")
    slides.append(s6.to_xml())

    # =========================================================================
    # SLIDE 7: CURRENT MONTH SNAPSHOT — HEADCOUNT & COST BY BUSINESS UNIT
    # =========================================================================
    s7 = OpenXmlSlideBuilder(7, period_label=period_title)
    s7.add_header_chrome(
        "SBU LABOR COST MATRIX",
        f"{period_title} Snapshot — Workforce Headcount & Cost by Business Unit",
        "Complete 15-column corporate labor cost report and Business Unit share pie charts"
    )
    t7_headers = [
        "Business Unit", "Beg", "+Hire", "-Sep", "End", "Basic", "Allow.",
        "Overtime", "Health", "Soc.Sec", "EOS", "Other", "Total Cost", "Avg Ex.EOS", "OT %"
    ]
    t7_rows = []
    for r in lcr:
        t7_rows.append([
            r.get("sbu_name_en") or r.get("sbu_display_name"),
            str(r.get("beginning_hc", 0)),
            f"+{r.get('new_hires', 0)}",
            f"-{r.get('separations', 0)}",
            str(r.get("ending_hc", 0)),
            _fmt_num(r.get("basic_salary", 0), 0),
            _fmt_num(r.get("allowances", 0), 0),
            _fmt_num(r.get("overtime_amount", 0), 0),
            _fmt_num(r.get("health_ins_comp", 0), 0),
            _fmt_num(r.get("social_security_comp", 0), 0),
            _fmt_num(r.get("eos_amount", 0), 0),
            _fmt_num(r.get("other_adjustments", 0), 0),
            _fmt_num(r.get("total_workforce_cost", 0), 0),
            _fmt_num(r.get("underlying_avg_cost_per_emp", 0), 0),
            f"{float(r.get('overtime_cost_pct') or 0.0):.1f}%",
        ])
    t7_rows.append([
        "TOTAL / AVG",
        str(lct.get("beginning_hc", 0)),
        f"+{lct.get('new_hires', 0)}",
        f"-{lct.get('separations', 0)}",
        str(lct.get("ending_hc", 0)),
        _fmt_num(lct.get("basic_salary", 0), 0),
        _fmt_num(lct.get("allowances", 0), 0),
        _fmt_num(lct.get("overtime_amount", 0), 0),
        _fmt_num(lct.get("health_ins_comp", 0), 0),
        _fmt_num(lct.get("social_security_comp", 0), 0),
        _fmt_num(lct.get("eos_amount", 0), 0),
        _fmt_num(lct.get("other_adjustments", 0), 0),
        _fmt_num(lct.get("total_workforce_cost", 0), 0),
        _fmt_num(lct.get("underlying_avg_cost_per_emp", 0), 0),
        f"{float(lct.get('overtime_cost_pct') or 0.0):.2f}%",
    ])
    s7.add_table_grid(
        24, 64, 912,
        [128, 36, 38, 36, 38, 66, 58, 56, 48, 58, 52, 46, 76, 62, 46],
        t7_headers, t7_rows, row_h=24.0, header_h=24.0,
        total_row_indices=[len(t7_rows) - 1], font_size=6.8, header_font_size=6.8
    )

    # Bottom Left: Total Cost Share by SBU Pie Chart
    sbu_cost_slices = [
        {
            "label": r.get("sbu_name_en") or r.get("sbu_display_name"),
            "value": float(r.get("total_workforce_cost") or 0.0),
            "color": sbu_colors[i % len(sbu_colors)],
        }
        for i, r in enumerate(lcr)
    ]
    s7.add_pie_donut_chart(
        24, 244, 448, 264,
        f"Total Workforce Cost Share by Business Unit — {period_title}",
        "Proportion of corporate payroll spend across the 5 Strategic Business Units",
        sbu_cost_slices,
        center_top=f"{_fmt_num(rep_cost, 0)}",
        center_bottom="Total JOD",
        header_hex="0F172A"
    )

    # Bottom Right: Ending Headcount Share by SBU Pie Chart
    sbu_hc_slices = [
        {
            "label": r.get("sbu_name_en") or r.get("sbu_display_name"),
            "value": float(r.get("ending_hc") or 0.0),
            "val_str": f"{int(r.get('ending_hc') or 0)} Emp",
            "color": sbu_colors[i % len(sbu_colors)],
        }
        for i, r in enumerate(lcr)
    ]
    s7.add_pie_donut_chart(
        486, 244, 450, 264,
        f"Ending Headcount Share by Business Unit — {period_title}",
        "Distribution of active workforce across the 5 Strategic Business Units",
        sbu_hc_slices,
        center_top=f"{end_hc:,}",
        center_bottom="Employees",
        header_hex="1E3A8A"
    )
    slides.append(s7.to_xml())

    # =========================================================================
    # SLIDE 8: KEY TAKEAWAYS & MANAGEMENT PRIORITIES
    # =========================================================================
    s8 = OpenXmlSlideBuilder(8, period_label=period_title)
    s8.add_header_chrome(
        "BOARD PRIORITIES",
        f"{period_title} Key Takeaways & Recommended Management Priorities",
        "Executive synthesis across Headcount, Cost Structure, and Operational Productivity"
    )
    pillars = [
        (
            "PILLAR 1: HEADCOUNT & MOVEMENT",
            "1E40AF",
            f"• Beginning HC: {beg_hc}  |  Ending HC: {end_hc} ({net_hc_diff:+d} Net)\n"
            f"• Gross Additions: +{new_hires}  |  Separations: -{separations}\n"
            f"• Monthly Turnover Rate: {turnover_rate:.1f}% ({vol_pct:.0f}% Voluntary)\n"
            f"• Hiring velocity maintained {repl_ratio:.2f}x replacement coverage."
        ),
        (
            "PILLAR 2: COST & STATUTORY STRUCTURE",
            "0F766E",
            f"• Reported Payroll: {_fmt_num(rep_cost, 0)} JOD\n"
            f"• EOS Settlements: {_fmt_num(eos_cost, 0)} JOD ({eos_share_pct:.1f}%)\n"
            f"• Underlying Cost: {_fmt_num(und_cost, 0)} JOD ({_fmt_num(und_avg, 0)} JOD/Emp)\n"
            f"• Co. Social Security (14.25%): {_fmt_num(lct.get('social_security_comp', 0), 0)} JOD"
        ),
        (
            "PILLAR 3: OVERTIME & PRODUCTIVITY",
            "B45309",
            f"• Total Overtime Spend: {_fmt_num(ot_cost, 0)} JOD\n"
            f"• Overtime Share of Total Cost: {ot_pct:.2f}%\n"
            f"• Top OT Unit: {top_ot_bu.get('sbu_name_en', 'N/A')} ({_fmt_num(top_ot_bu.get('overtime_amount', 0), 0)} JOD)\n"
            f"• Company Health Insurance: {_fmt_num(lct.get('health_ins_comp', 0), 0)} JOD"
        ),
    ]
    for idx, (ptitle, pcol, pbody) in enumerate(pillars):
        px = 24 + idx * 308
        s8.add_rect(px, 66, 296, 178, fill_hex="FFFFFF", line_hex="CBD5E1", round_radius=5000)
        s8.add_rect(px, 66, 296, 26, fill_hex=pcol)
        s8.add_text(px + 10, 69, 276, 20, ptitle, size_pt=8.2, color_hex="FFFFFF", bold=True, valign="ctr")
        s8.add_text(px + 12, 98, 272, 138, pbody, size_pt=8.6, color_hex="0F172A", valign="t")

    # Bottom: 4 Recommended Board Priorities
    s8.add_rect(24, 256, 912, 26, fill_hex="0F172A")
    s8.add_text(36, 259, 888, 20, "RECOMMENDED BOARD & MANAGEMENT PRIORITIES (NEXT 30–90 DAYS)", size_pt=9.0, color_hex="FFFFFF", bold=True, valign="ctr")

    raw_priorities = ins.get("priorities") or [
        "Validate workforce capacity requirements in Delta Factory and Retail branches.",
        "Analyze monthly separations, focusing on voluntary resignations and critical-role exits.",
        "Track Underlying Workforce Cost (excluding EOS settlements) separately for accurate month-over-month comparability.",
        "Monitor Retail overtime by branch, shift, and attendance logs.",
    ]
    p_titles = [
        "1. Capacity & Workforce Alignment",
        "2. Retention & Voluntary Turnover Control",
        "3. Underlying Cost & EOS Governance",
        "4. Overtime & Shift Roster Optimization",
    ]
    p_colors = ["1E40AF", "0D9488", "7C3AED", "D97706"]
    for idx in range(4):
        col_i = idx % 2
        row_i = idx // 2
        bx = 24 + col_i * 462
        by = 290 + row_i * 110
        pr_item = raw_priorities[idx] if idx < len(raw_priorities) else ""
        if isinstance(pr_item, dict):
            pt = pr_item.get("title") or p_titles[idx]
            pd = pr_item.get("desc") or ""
        else:
            pt = p_titles[idx]
            pd = str(pr_item)
        s8.add_rect(bx, by, 450, 102, fill_hex="FFFFFF", line_hex="CBD5E1", round_radius=5000)
        s8.add_rect(bx, by, 8, 102, fill_hex=p_colors[idx % len(p_colors)])
        s8.add_text(bx + 18, by + 8, 420, 22, pt, size_pt=9.5, color_hex="0F172A", bold=True, valign="ctr")
        s8.add_text(bx + 18, by + 32, 420, 62, pd, size_pt=8.3, color_hex="334155", valign="t")
    slides.append(s8.to_xml())

    # =========================================================================
    # SLIDE 9: TURNOVER & MOVEMENT ANALYSIS BY BUSINESS UNIT
    # =========================================================================
    s9 = OpenXmlSlideBuilder(9, period_label=period_title)
    s9.add_header_chrome(
        "TURNOVER MATRIX",
        f"{period_title} Workforce Movement & Turnover Risk by Business Unit",
        "Business Unit headcount bridge, monthly turnover rate ranking, and RAG risk assessment"
    )
    t9_headers = [
        "Business Unit", "Beg. HC", "+ New Hires", "- Separations", "Ending HC",
        "Net Change", "Turnover %", "Voluntary %", "Critical Exits", "Risk Assessment"
    ]
    t9_rows = []
    hbar_items = []
    for r in lcr:
        risk_lbl = r.get("rag_label", "Optimal / Stable")
        rag_st = r.get("rag_status", "optimal")
        rcell = (
            {"text": risk_lbl.upper(), "bg": "FEE2E2", "fg": "991B1B", "bold": True, "align": "c"}
            if rag_st == "critical" else
            ({"text": risk_lbl.upper(), "bg": "FEF3C7", "fg": "92400E", "bold": True, "align": "c"}
             if rag_st == "monitor" else
             {"text": risk_lbl.upper(), "bg": "D1FAE5", "fg": "065F46", "bold": True, "align": "c"})
        )
        net_v = int(r.get("net_movement") or 0)
        t9_rows.append([
            r.get("sbu_name_en") or r.get("sbu_display_name"),
            str(r.get("beginning_hc", 0)),
            {"text": f"+{r.get('new_hires', 0)}", "bg": "F0FDF4", "fg": "166534", "bold": True, "align": "c"},
            {"text": f"-{r.get('separations', 0)}", "bg": "FEF2F2", "fg": "991B1B", "bold": True, "align": "c"},
            str(r.get("ending_hc", 0)),
            f"{net_v:+d}",
            f"{float(r.get('turnover_rate') or 0.0):.1f}%",
            f"{float(r.get('voluntary_share_pct') or 0.0):.0f}%",
            str(r.get("critical_departures", 0)),
            rcell,
        ])
        hbar_items.append({
            "label": r.get("sbu_name_en") or r.get("sbu_display_name"),
            "value": float(r.get("turnover_rate") or 0.0),
            "color": "DC2626" if rag_st == "critical" else ("D97706" if rag_st == "monitor" else "059669"),
        })

    t9_rows.append([
        "TOTAL CORPORATE",
        str(beg_hc),
        f"+{new_hires}",
        f"-{separations}",
        str(end_hc),
        f"{net_hc_diff:+d}",
        f"{turnover_rate:.1f}%",
        f"{vol_pct:.0f}%",
        str(wm.get("critical_departures", 0)),
        {"text": f"{turnover_rate:.1f}% OVERALL", "bg": "0F172A", "fg": "FFFFFF", "bold": True, "align": "c"},
    ])
    s9.add_table_grid(
        24, 64, 912, [175, 68, 78, 82, 72, 74, 78, 78, 82, 125],
        t9_headers, t9_rows, row_h=24.0, header_h=24.0,
        total_row_indices=[len(t9_rows) - 1], font_size=7.2
    )

    # Bottom Left: Horizontal Bar Chart of Turnover Rate % by SBU
    s9.add_horizontal_bar_chart(
        24, 244, 448, 264,
        f"Monthly Turnover Rate (%) by Business Unit — {period_title}",
        "Color-segmented by risk threshold (Red = Critical, Amber = Monitor, Green = Stable)",
        hbar_items,
        header_hex="0F172A",
        suffix="%"
    )

    # Bottom Right: Grouped Column Chart — Hires vs Separations by SBU
    s9.add_grouped_column_chart(
        486, 244, 450, 264,
        f"New Hires vs. Separations by Business Unit — {period_title}",
        "Comparison of monthly onboarding against employee exits per SBU",
        [(r.get("sbu_name_en") or "").replace("Retail ", "Ret. ").replace("Factory", "Fact.")[:12] for r in lcr],
        [
            {"name": "New Hires (+)", "values": [float(r.get("new_hires") or 0) for r in lcr], "color": "059669"},
            {"name": "Separations (-)", "values": [float(r.get("separations") or 0) for r in lcr], "color": "DC2626"},
        ],
        header_hex="1E3A8A",
        decimals=0
    )
    slides.append(s9.to_xml())

    # =========================================================================
    # SLIDE 10: TURNOVER DEEP-DIVE (VOLUNTARY PIE CHART & RETENTION PLAN)
    # =========================================================================
    s10 = OpenXmlSlideBuilder(10, period_label=period_title)
    s10.add_header_chrome(
        "RETENTION ACTION PLAN",
        f"Turnover Deep-Dive: Voluntary vs. Involuntary & Action Plan — {period_title}",
        "Exit classification pie charts, critical role attrition, and 3-pillar retention roadmap"
    )
    vol_cnt = int(wm.get("voluntary_separations") or lct.get("voluntary_separations") or 0)
    invol_cnt = max(separations - vol_cnt, 0)
    crit_cnt = int(wm.get("critical_departures") or lct.get("critical_departures") or 0)
    non_crit_cnt = max(separations - crit_cnt, 0)

    # Top Left: Voluntary vs Involuntary Pie Chart
    vol_slices = [
        {"label": "Voluntary Resignations", "value": float(vol_cnt if separations > 0 else 1), "val_str": f"{vol_cnt} Exits", "color": "DC2626"},
        {"label": "Involuntary / Contract End", "value": float(invol_cnt), "val_str": f"{invol_cnt} Exits", "color": "D97706"},
    ]
    s10.add_pie_donut_chart(
        24, 66, 448, 214,
        f"Voluntary vs. Involuntary Separations — {period_title}",
        "Share of controllable resignations vs. company-initiated separations",
        vol_slices,
        center_top=f"{vol_pct:.0f}%",
        center_bottom="Voluntary",
        header_hex="991B1B"
    )

    # Bottom Left: Critical Role vs Standard Role Exits Pie Chart
    crit_slices = [
        {"label": "Critical / Supervisory Exits", "value": float(crit_cnt), "val_str": f"{crit_cnt} Exits", "color": "7C3AED"},
        {"label": "Standard Operational Exits", "value": float(max(non_crit_cnt, 1 if separations == 0 else 0)), "val_str": f"{non_crit_cnt} Exits", "color": "2563EB"},
    ]
    s10.add_pie_donut_chart(
        24, 290, 448, 218,
        f"Critical Role vs. Standard Role Separations — {period_title}",
        "Monitors leadership, specialist, branch manager, and production supervisor exits",
        crit_slices,
        center_top=f"{crit_cnt}",
        center_bottom="Critical Exits",
        header_hex="4F46E5"
    )

    # Right Panel: 3-Stage Retention & Stabilization Action Plan
    action_cards = [
        (
            "STAGE 1: IMMEDIATE EXIT & STAY INTERVIEWS (DAYS 1–30)",
            "DC2626",
            f"• Voluntary resignations represent {vol_pct:.0f}% ({vol_cnt} of {separations} exits) in {period_title}.\n"
            f"• Conduct mandatory structured HR exit interviews for 100% of resigning staff.\n"
            f"• Deploy proactive stay interviews in branches/lines showing >2.5% monthly turnover."
        ),
        (
            "STAGE 2: FIRST-90-DAY NEW HIRE INTEGRATION (DAYS 30–60)",
            "0D9488",
            f"• Protect the current cohort of +{new_hires} new hires onboarded in {period_title}.\n"
            f"• Pair every new factory operator and retail sales associate with a shift mentor.\n"
            f"• Track 30/60/90-day probation completion to eliminate early-tenure churn."
        ),
        (
            "STAGE 3: CRITICAL ROLE PROTECTION & WORKLOAD BALANCING (DAYS 60–90)",
            "1E40AF",
            f"• {crit_cnt} critical/supervisory exits recorded in {period_title}.\n"
            f"• Maintain bench succession coverage for Branch Managers, Production Supervisors, and Finance/HR specialists.\n"
            f"• Rebalance shift schedules to reduce overtime ({ot_pct:.2f}% of cost) and prevent burnout."
        ),
    ]
    for idx, (atitle, acol, abody) in enumerate(action_cards):
        ay = 66 + idx * 149
        s10.add_rect(486, ay, 450, 142, fill_hex="FFFFFF", line_hex="CBD5E1", round_radius=5000)
        s10.add_rect(486, ay, 450, 25, fill_hex=acol)
        s10.add_text(496, ay + 3, 430, 19, atitle, size_pt=8.2, color_hex="FFFFFF", bold=True, valign="ctr")
        s10.add_text(496, ay + 30, 430, 106, abody, size_pt=8.6, color_hex="0F172A", valign="t")
    slides.append(s10.to_xml())

    return _package_pptx_zip(slides)


def _package_pptx_zip(slide_xml_list):
    """Packages a list of slide XML strings into a valid OpenXML .pptx archive."""
    buf = io.BytesIO()
    num_slides = len(slide_xml_list)

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. [Content_Types].xml
        slide_overrides = "".join(
            f'<Override PartName="/ppt/slides/slide{i}.xml" '
            f'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
            for i in range(1, num_slides + 1)
        )
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
            '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
            '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
            '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
            '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
            '<Override PartName="/ppt/presProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"/>'
            '<Override PartName="/ppt/viewProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"/>'
            '<Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/>'
            f'{slide_overrides}'
            '</Types>'
        )
        zf.writestr("[Content_Types].xml", content_types)

        # 2. _rels/.rels
        root_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
            '</Relationships>'
        )
        zf.writestr("_rels/.rels", root_rels)

        # 3. ppt/_rels/presentation.xml.rels
        slide_rels = "".join(
            f'<Relationship Id="rIdSlide{i}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
            f'Target="slides/slide{i}.xml"/>'
            for i in range(1, num_slides + 1)
        )
        pres_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rIdMaster1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
            '<Relationship Id="rIdTheme1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>'
            '<Relationship Id="rIdPresProps" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps" Target="presProps.xml"/>'
            '<Relationship Id="rIdViewProps" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps" Target="viewProps.xml"/>'
            '<Relationship Id="rIdTableStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles" Target="tableStyles.xml"/>'
            f'{slide_rels}'
            '</Relationships>'
        )
        zf.writestr("ppt/_rels/presentation.xml.rels", pres_rels)

        # 4. ppt/presentation.xml (16:9 widescreen 12192000 x 6858000)
        sld_ids = "".join(
            f'<p:sldId id="{255 + i}" r:id="rIdSlide{i}"/>'
            for i in range(1, num_slides + 1)
        )
        pres_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
            'saveSubsetFonts="1">'
            '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rIdMaster1"/></p:sldMasterIdLst>'
            f'<p:sldIdLst>{sld_ids}</p:sldIdLst>'
            '<p:sldSz cx="12192000" cy="6858000" type="screen16x9"/>'
            '<p:notesSz cx="6858000" cy="9144000"/>'
            '</p:presentation>'
        )
        zf.writestr("ppt/presentation.xml", pres_xml)

        # 5. ppt/presProps.xml, viewProps.xml, tableStyles.xml
        zf.writestr(
            "ppt/presProps.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:presProps xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>'
        )
        zf.writestr(
            "ppt/viewProps.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:viewProps xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>'
        )
        zf.writestr(
            "ppt/tableStyles.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>'
        )

        # 6. Slide Master & Slide Layout
        zf.writestr(
            "ppt/slideMasters/_rels/slideMaster1.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rIdLayout1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
            '<Relationship Id="rIdTheme1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>'
            '</Relationships>'
        )
        zf.writestr(
            "ppt/slideMasters/slideMaster1.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:cSld><p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>'
            '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            '</p:spTree></p:cSld>'
            '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
            '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rIdLayout1"/></p:sldLayoutIdLst>'
            '</p:sldMaster>'
        )
        zf.writestr(
            "ppt/slideLayouts/_rels/slideLayout1.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rIdMaster1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>'
            '</Relationships>'
        )
        zf.writestr(
            "ppt/slideLayouts/slideLayout1.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">'
            '<p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>'
            '</p:sldLayout>'
        )

        # 7. Theme
        zf.writestr(
            "ppt/theme/theme1.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="AnabtawiExecutiveTheme">'
            '<a:themeElements>'
            '<a:clrScheme name="Anabtawi">'
            '<a:dk1><a:srgbClr val="0F172A"/></a:dk1>'
            '<a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>'
            '<a:dk2><a:srgbClr val="1E293B"/></a:dk2>'
            '<a:lt2><a:srgbClr val="F1F5F9"/></a:lt2>'
            '<a:accent1><a:srgbClr val="2563EB"/></a:accent1>'
            '<a:accent2><a:srgbClr val="0D9488"/></a:accent2>'
            '<a:accent3><a:srgbClr val="7C3AED"/></a:accent3>'
            '<a:accent4><a:srgbClr val="D97706"/></a:accent4>'
            '<a:accent5><a:srgbClr val="DC2626"/></a:accent5>'
            '<a:accent6><a:srgbClr val="059669"/></a:accent6>'
            '<a:hlink><a:srgbClr val="2563EB"/></a:hlink>'
            '<a:folHlink><a:srgbClr val="7C3AED"/></a:folHlink>'
            '</a:clrScheme>'
            '<a:fontScheme name="AnabtawiFonts">'
            '<a:majorFont><a:latin typeface="Segoe UI"/><a:ea typeface="Segoe UI"/><a:cs typeface="Segoe UI"/></a:majorFont>'
            '<a:minorFont><a:latin typeface="Segoe UI"/><a:ea typeface="Segoe UI"/><a:cs typeface="Segoe UI"/></a:minorFont>'
            '</a:fontScheme>'
            '<a:fmtScheme name="AnabtawiFmt">'
            '<a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
            '<a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>'
            '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
            '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>'
            '</a:fmtScheme>'
            '</a:themeElements>'
            '</a:theme>'
        )

        # 8. Slides & Slide Relationships
        slide_rel_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
            '</Relationships>'
        )
        for idx, s_xml in enumerate(slide_xml_list, start=1):
            zf.writestr(f"ppt/slides/slide{idx}.xml", s_xml)
            zf.writestr(f"ppt/slides/_rels/slide{idx}.xml.rels", slide_rel_xml)

    buf.seek(0)
    return buf.read()
