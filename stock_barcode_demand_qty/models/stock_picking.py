from odoo import fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    barcode_demand_locked = fields.Boolean(
        string="تم تأكيد الكمية المطلوبة",
        copy=False,
        help="When set, barcode scans fill the done quantity instead of the factory demand.",
    )
    barcode_show_demand_qty = fields.Boolean(
        related="picking_type_id.barcode_show_demand_qty",
    )

    def _get_fields_stock_barcode(self):
        return super()._get_fields_stock_barcode() + ["barcode_demand_locked"]

    def _check_barcode_demand_action(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "stock_barcode_demand_qty.group_barcode_demand_confirm"
        ):
            raise UserError(self.env._("ليس لديك صلاحية تأكيد الكمية المطلوبة."))
        if self.state in ("done", "cancel"):
            raise UserError(self.env._("لا يمكن تعديل طلب مكتمل أو ملغى."))
        if not self.picking_type_id.barcode_show_demand_qty:
            raise UserError(self.env._("نوع العملية هذا لا يستخدم الكمية المطلوبة في الباركود."))

    def _factory_qty_started(self):
        self.ensure_one()
        return bool(
            self.move_line_ids.filtered(lambda line: line.product_id and line.picked)
        )

    def action_barcode_confirm_demand(self):
        for picking in self:
            picking._check_barcode_demand_action()
            if picking.barcode_demand_locked:
                continue
            lines = picking.move_line_ids.filtered("product_id")
            if not any(line.demand_qty for line in lines):
                raise UserError(self.env._("أدخل الكمية المطلوبة قبل التأكيد."))
            open_lines = lines.filtered(lambda line: line.state not in ("done", "cancel"))
            if open_lines:
                open_lines.write({"quantity": 0, "picked": False})
            open_lines.filtered("demand_qty")._sync_demand_qty_to_move()
            picking.barcode_demand_locked = True
        return True

    def action_barcode_edit_demand(self):
        for picking in self:
            picking._check_barcode_demand_action()
            if not picking.barcode_demand_locked:
                continue
            if picking._factory_qty_started():
                raise UserError(
                    self.env._("لا يمكن تعديل الكمية المطلوبة بعد إدخال كمية المصنع.")
                )
            picking.barcode_demand_locked = False
        return True
