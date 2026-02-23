# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare

_ALLOWED_CODES = {"incoming", "outgoing", "internal"}

class StockMove(models.Model):
    _inherit = "stock.move"

    @api.onchange("quantity_done", "product_uom_qty")
    def _onchange_block_over_done_ops(self):
        """يغطي Operations (سطر العملية)"""
        for move in self:
            if not move.picking_id or move.picking_type_id.code not in _ALLOWED_CODES:
                continue
            if float_compare(move.quantity_done, move.product_uom_qty,
                             precision_rounding=move.product_uom.rounding) > 0:
                move.quantity_done = move.product_uom_qty
                return {
                    "warning": {
                        "title": _("تنبيه"),
                        "message": _("لا يمكن أن تكون الكمية المنجزة أكبر من الكمية المطلوبة (Demand)."),
                    }
                }

    @api.constrains("quantity_done", "product_uom_qty", "picking_id")
    def _check_block_over_done_ops(self):
        """قيد نهائي يغطي Operations + أي تعديل خارجي"""
        for move in self:
            if not move.picking_id or move.picking_type_id.code not in _ALLOWED_CODES:
                continue
            if float_compare(move.quantity_done, move.product_uom_qty,
                             precision_rounding=move.product_uom.rounding) > 0:
                raise ValidationError(_(
                    "ممنوع إدخال كمية منجزة أكبر من الكمية المطلوبة.\n"
                    "المنتج: %(p)s\nالمطلوب: %(d)s %(u)s\nالمنجز: %(q)s %(u)s",
                    p=move.product_id.display_name,
                    d=move.product_uom_qty,
                    q=move.quantity_done,
                    u=move.product_uom.name,
                ))


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    @api.onchange("qty_done", "move_id", "product_uom_id")
    def _onchange_block_over_done_detailed(self):
        """يغطي Detailed Operations (سطور التفاصيل) مع حساب باقي المسموح"""
        for line in self:
            move = line.move_id
            if not move or not move.picking_id or move.picking_type_id.code not in _ALLOWED_CODES:
                continue

            # إجمالي المنجز لباقي السطور (بدون السطر الحالي) بعد تحويل UoM
            other_total = 0.0
            for ml in move.move_line_ids.filtered(lambda x: x != line and x.state != "cancel"):
                other_total += ml.product_uom_id._compute_quantity(ml.qty_done, move.product_uom)

            # تحويل qty_done للسطر الحالي إلى UoM الحركة
            this_done = line.product_uom_id._compute_quantity(line.qty_done, move.product_uom)

            allowed = move.product_uom_qty - other_total
            if allowed < 0:
                allowed = 0.0

            if float_compare(this_done, allowed, precision_rounding=move.product_uom.rounding) > 0:
                # نعيد ضبط السطر الحالي لأقصى قيمة مسموحة
                new_qty = move.product_uom._compute_quantity(allowed, line.product_uom_id)
                line.qty_done = new_qty
                return {
                    "warning": {
                        "title": _("تنبيه"),
                        "message": _("لا يمكن أن يتجاوز مجموع Done قيمة Demand. تم ضبط الكمية للحد المسموح."),
                    }
                }

    @api.constrains("qty_done", "move_id", "product_uom_id")
    def _check_block_over_done_detailed(self):
        """قيد نهائي يمنع أن مجموع done على كل سطور الحركة يتجاوز demand"""
        for line in self:
            move = line.move_id
            if not move or not move.picking_id or move.picking_type_id.code not in _ALLOWED_CODES:
                continue

            done_total = 0.0
            for ml in move.move_line_ids.filtered(lambda x: x.state != "cancel"):
                done_total += ml.product_uom_id._compute_quantity(ml.qty_done, move.product_uom)

            if float_compare(done_total, move.product_uom_qty,
                             precision_rounding=move.product_uom.rounding) > 0:
                raise ValidationError(_(
                    "ممنوع أن يتجاوز مجموع الكمية المنجزة الكمية المطلوبة.\n"
                    "المنتج: %(p)s\nالمطلوب: %(d)s %(u)s\nمجموع المنجز: %(q)s %(u)s",
                    p=move.product_id.display_name,
                    d=move.product_uom_qty,
                    q=done_total,
                    u=move.product_uom.name,
                ))
