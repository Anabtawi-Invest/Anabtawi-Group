# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class PosPledge(models.Model):
    _name = "pos.pledge"
    _description = "POS Pledge (Rahn) Record"
    _order = "create_date desc"

    name = fields.Char(
        string="Pledge Reference",
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _("New"),
    )

    pos_order_id = fields.Many2one(
        "pos.order",
        string="POS Order",
        required=True,
        ondelete="cascade",
    )
    pos_config_id = fields.Many2one(
        "pos.config",
        string="POS Configuration",
        required=True,
        readonly=True,
    )

    partner_id = fields.Many2one("res.partner", string="Customer", required=True)
    employee_id = fields.Many2one("hr.employee", string="Employee")

    pledge_products = fields.Many2many(
        "product.product",
        string="Pledge Products",
        domain=[("has_pledge", "=", True)],
    )
    employee_product_id = fields.Many2one(
        "product.product",
        string="Employee Service",
        domain=[("is_employee_service", "=", True)],
    )
    delivery_product_id = fields.Many2one(
        "product.product",
        string="Delivery Service",
        domain=[("is_delivery_product", "=", True)],
    )

    pledge_amount = fields.Monetary(string="Pledge Amount", required=True)
    employee_amount = fields.Monetary(string="Employee Service Amount")
    delivery_amount = fields.Monetary(string="Delivery Service Amount")

    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
    )
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        required=True,
    )

    state = fields.Selection(
        [
            ("active", "Active"),
            ("returned", "Returned"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="active",
        required=True,
    )

    # Payment tracking (kept because views reference them)
    pledge_payment_id = fields.Many2one("account.payment", string="Pledge Payment", readonly=True)
    employee_payment_id = fields.Many2one("account.payment", string="Employee Payment", readonly=True)
    delivery_payment_id = fields.Many2one("account.payment", string="Delivery Payment", readonly=True)
    return_payment_id = fields.Many2one("account.payment", string="Return/Refund Payment", readonly=True)

    # Legacy journal entry fields (views reference them)
    pledge_move_id = fields.Many2one("account.move", string="Pledge Journal Entry (Legacy)", readonly=True)
    employee_move_id = fields.Many2one("account.move", string="Employee Journal Entry (Legacy)", readonly=True)
    delivery_move_id = fields.Many2one("account.move", string="Delivery Journal Entry (Legacy)", readonly=True)
    return_move_id = fields.Many2one("account.move", string="Return Journal Entry (Legacy)", readonly=True)

    return_date = fields.Datetime(string="Return Date", readonly=True)

    case_type = fields.Selection(
        [
            ("case1", "Case 1: Employee Only"),
            ("case2", "Case 2: Pledge Only"),
            ("case3", "Case 3: Pledge + Delivery"),
            ("case4", "Case 4: Pledge + Employee + Delivery"),
            ("case5", "Case 5: Pledge + Employee"),
            ("case6", "Case 6: Employee + Delivery"),
            ("mixed", "Mixed Scenario"),
        ],
        string="Business Case",
        required=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("pos.pledge") or _("New")
        return super().create(vals_list)

    @api.model
    def create_from_pos(self, vals):
        """
        Create pledge header record from POS frontend.

        This method is called by pos_pledge JS. It creates the tracking record only.
        (Any accounting/payment logic is handled elsewhere in the module.)
        """
        pos_order_id = vals.get("pos_order_id")
        partner_id = vals.get("partner_id")
        case_type = vals.get("case_type")
        if not pos_order_id or not partner_id or not case_type:
            raise ValidationError(_("Missing required fields for pledge creation"))

        pos_order = self.env["pos.order"].sudo().browse(pos_order_id)
        if not pos_order.exists():
            raise ValidationError(_("POS Order not found"))

        pledge = self.sudo().create({
            "pos_order_id": pos_order.id,
            "pos_config_id": pos_order.config_id.id,
            "partner_id": partner_id,
            "employee_id": pos_order.employee_id.id if pos_order.employee_id else False,
            "case_type": case_type,
            "pledge_amount": vals.get("pledge_amount", 0.0) or 0.0,
            "employee_amount": vals.get("employee_amount", 0.0) or 0.0,
            "delivery_amount": vals.get("delivery_amount", 0.0) or 0.0,
            "pledge_products": [(6, 0, vals.get("pledge_products", []) or [])],
            "employee_product_id": vals.get("employee_product_id") or False,
            "delivery_product_id": vals.get("delivery_product_id") or False,
            "company_id": pos_order.company_id.id,
            "currency_id": pos_order.currency_id.id or pos_order.company_id.currency_id.id,
        })

        _logger.info("[PLEDGE] Created pos.pledge %s for pos.order %s", pledge.name, pos_order.name)
        return pledge.id

    def action_cancel(self):
        self.write({"state": "cancelled"})
        return True

    def action_return_pledge(self):
        """Reverse posted pledge deposit move and mark pledge returned."""
        for pledge in self:
            if pledge.state == "returned" and pledge.return_move_id:
                continue
            if pledge.state != "active":
                raise UserError(_("Only active pledges can be returned: %s") % pledge.name)
            if pledge.return_move_id:
                continue
            move = pledge.pledge_move_id
            if not move or move.state != "posted":
                raise UserError(
                    _("No posted pledge journal entry is linked to %s. Cannot reverse.") % pledge.name
                )
            move_sudo = move.sudo()
            reverse_moves = move_sudo._reverse_moves(
                [{
                    "date": fields.Date.context_today(pledge),
                    "ref": _("Pledge return - %s") % pledge.name,
                }],
                cancel=False,
            )
            reverse_moves.sudo().action_post()
            pledge.write({
                "state": "returned",
                "return_date": fields.Datetime.now(),
                "return_move_id": reverse_moves[:1].id,
            })
            po = pledge.pos_order_id
            if po and po.session_id and po.session_id.state in ("opened", "closing_control"):
                po.session_id.invalidate_recordset(
                    ["cash_register_balance_end", "cash_register_difference"]
                )
        return True

    def action_link_payments(self):
        # Kept as a placeholder (button exists in view); actual logic is in pos.order flow.
        return True

