# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.fields import Domain
from odoo.exceptions import UserError
from odoo.fields import Command

_logger = logging.getLogger(__name__)


class PosAdvanceOrder(models.Model):
    _name = "pos.advance.order"
    _description = "POS Advance Order"
    _inherit = ["product.catalog.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="Reference", required=True, readonly=True, default="New")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("advance_paid", "Advance Paid"),
            ("fully_paid", "Fully Paid"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        required=True,
        readonly=True,
    )

    def init(self):
        # Data cleanup: older versions had a 'refunded' state. We now map it to 'cancel'.
        # This runs at registry init (install/upgrade) and is idempotent.
        self.env.cr.execute(
            "UPDATE pos_advance_order SET state = 'cancel' WHERE state = 'refunded'"
        )

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )

    partner_id = fields.Many2one("res.partner", string="Customer", required=True)
    user_id = fields.Many2one(
        "res.users",
        string="Responsible",
        default=lambda self: self.env.user,
        required=True,
    )
    picking_date = fields.Datetime(string="Picking Date", required=True, default=fields.Datetime.now)
    pos_config_id = fields.Many2one("pos.config", string="Picking POS", required=True)
    pos_config_enable_advance_order = fields.Boolean(
        string="Picking POS Enable Advance Order",
        related="pos_config_id.enable_advance_order",
        readonly=True,
    )
    pricelist_id = fields.Many2one(
        "product.pricelist",
        string="Pricelist",
        related="pos_config_id.pricelist_id",
        store=True,
        readonly=True,
    )
    is_employee_pricelist = fields.Boolean(
        string="Is Employee Pricelist",
        default=False,
        help="If enabled, you can apply the Employee Pricelist (from the POS config) after employee password verification.",
    )
    employee_pricelist_employee_id = fields.Many2one(
        "hr.employee",
        string="Employee (Pricelist Authorization)",
        readonly=True,
        copy=False,
        help="Employee who authorized applying the employee pricelist on this advance order.",
    )

    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="pos_config_id.currency_id",
        store=True,
        readonly=True,
    )
    with_employee = fields.Boolean(string="With Employee", default=False)
    employee_id = fields.Many2one("hr.employee", string="Employee")
    payment_method = fields.Selection(
        [
            ("cash", "Cash"),
            ("bank", "Bank"),
        ],
        string="Payment Type (legacy)",
        required=True,
        default="cash",
        help="Derived from the POS payment method when set. Kept for compatibility with older data.",
    )
    pos_payment_method_id = fields.Many2one(
        "pos.payment.method",
        string="POS Payment Method",
        domain="[('company_id', '=', company_id)]",
        help="Payment method used for the advance, matching the current POS configuration / session.",
    )

    line_ids = fields.One2many(
        "pos.advance.order.line",
        "order_id",
        string="Lines",
        copy=True,
    )

    amount_products = fields.Monetary(string="Products Total", currency_field="currency_id", compute="_compute_amounts", store=True)
    pledge_amount = fields.Monetary(string="Pledge Amount", currency_field="currency_id", compute="_compute_amounts", store=True)
    amount_total = fields.Monetary(string="Total", currency_field="currency_id", compute="_compute_amounts", store=True)
    amount_grand_total = fields.Monetary(string="Grand Total", currency_field="currency_id", compute="_compute_amounts", store=True)
    advance_amount = fields.Monetary(string="Advance", currency_field="currency_id", default=0.0)
    amount_paid = fields.Monetary(string="Paid Amount", currency_field="currency_id", compute="_compute_payment_amounts", store=True)
    amount_remaining = fields.Monetary(string="Remaining Amount", currency_field="currency_id", compute="_compute_payment_amounts", store=True)
    from_pos_config_id = fields.Many2one(
        "pos.config",
        string="From POS",
        help="POS used to register the advance (deposit). The first POS order/payment will be recorded in its currently opened session.",
    )
    advance_pos_order_id = fields.Many2one("pos.order", string="Advance POS Order", readonly=True, copy=False)
    remaining_pos_order_id = fields.Many2one("pos.order", string="Remaining POS Order", readonly=True, copy=False)
    pledge_pos_order_id = fields.Many2one("pos.order", string="Pledge POS Order", readonly=True, copy=False)
    refund_advance_pos_order_id = fields.Many2one("pos.order", string="Refund Advance POS Order", readonly=True, copy=False)
    return_pledge_pos_order_id = fields.Many2one("pos.order", string="Return Pledge POS Order", readonly=True, copy=False)
    advance_account_payment_id = fields.Many2one(
        "account.payment",
        string="Advance Account Payment",
        readonly=True,
        copy=False,
    )
    advance_liability_move_id = fields.Many2one(
        "account.move",
        string="Advance Liability Move",
        readonly=True,
        copy=False,
    )
    # Kept for UI (can be removed later). Now computed from POS orders rather than account.payment.
    payment_progress = fields.Selection(
        [("no_payment", "No Payment"), ("advance_paid", "Advance Paid"), ("fully_paid", "Fully Paid")],
        string="Payment Progress",
        compute="_compute_payment_progress",
        store=True,
        readonly=True,
    )
    pledge_line_ids = fields.One2many(
        "pos.advance.order.pledge",
        "order_id",
        string="Pledges",
        copy=False,
    )
    pledge_count = fields.Float(string="Pledges Count", compute="_compute_pledge_count", store=True)

    discount_id = fields.Many2one(
        "pos.advance.discount",
        string="Discount",
        domain="[('active','=',True), ('company_id','=',company_id)]",
    )

    discount_amount = fields.Monetary(
        string="Discount Amount",
        currency_field="currency_id",
        default=0.0,
    )


    def _get_effective_pricelist(self):
        """Return the pricelist that should be used for pricing this advance order.

        Default is the POS config pricelist (related field `pricelist_id`).
        If the user enabled employee pricelist and it was authorized via the wizard,
        we switch to the employee pricelist configured on the POS.
        """
        self.ensure_one()
        employee_pricelist = getattr(self.pos_config_id, "employee_pricelist_id", False)
        if self.is_employee_pricelist and self.employee_pricelist_employee_id and employee_pricelist:
            return employee_pricelist
        return self.pricelist_id

    def _apply_pricelist_to_lines(self, pricelist):
        """Apply given pricelist to all product lines (draft only)."""
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("You can only reprice lines on a Draft advance order."))
        if not pricelist:
            return
        for line in self.line_ids.filtered(lambda l: not l.display_type and l.product_id):
            qty = line.product_qty or 0.0
            if qty <= 0:
                continue
            line.price_unit = pricelist._get_product_price(
                product=line.product_id,
                quantity=max(qty, 1.0),
                currency=self.currency_id,
                uom=line.product_uom_id,
                date=self.picking_date,
            )

    def _send_create_payment_email_to_manager(self):
        """Notify the configured manager on the Picking POS when advance payment is created."""
        self.ensure_one()
        manager = getattr(self.pos_config_id, "advance_order_manager_id", False)
        if not manager:
            return

        email_to = manager.email or manager.partner_id.email
        if not email_to:
            return

        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "http://localhost:8069")
        order_link = f"{base_url}/web#id={self.id}&model=pos.advance.order&view_type=form"

        currency = self.currency_id
        partner = self.partner_id

        # Keep it simple (can be moved to a template later).
        lines_html = ""
        for l in self.line_ids.filtered(lambda x: not x.display_type and x.product_id):
            lines_html += (
                f"<tr>"
                f"<td style='padding:6px;border:1px solid #ddd'>{l.product_id.display_name}</td>"
                f"<td style='padding:6px;border:1px solid #ddd;text-align:center'>{l.product_qty:g}</td>"
                f"<td style='padding:6px;border:1px solid #ddd;text-align:right'>{currency.symbol} {l.price_unit:,.2f}</td>"
                f"<td style='padding:6px;border:1px solid #ddd;text-align:right'>{currency.symbol} {l.price_subtotal_incl:,.2f}</td>"
                f"</tr>"
            )

        pledge_html = ""
        if self.pledge_amount:
            pledge_html = f"<strong>Pledge Amount:</strong> {currency.symbol} {self.pledge_amount:,.2f}<br/>"

        body_html = f"""
            <div style="font-family: Arial, sans-serif; padding: 16px;">
                <h3 style="margin:0 0 10px 0;">Advance Payment Created</h3>
                <p style="margin:0 0 10px 0;">
                    <strong>Advance Order:</strong> {self.name}<br/>
                    <strong>Customer:</strong> {partner.display_name}<br/>
                    <strong>Phone:</strong> {partner.phone or "N/A"}<br/>
                    <strong>Paid (Advance):</strong> {currency.symbol} {self.advance_amount:,.2f}<br/>
                    <strong>Invoice Total:</strong> {currency.symbol} {self.amount_total:,.2f}<br/>
                    {pledge_html}
                    <strong>Remaining:</strong> {currency.symbol} {self.amount_remaining:,.2f}<br/>
                </p>

                <h4 style="margin:14px 0 6px 0;">Products</h4>
                <table style="width:100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background:#f7f7f7">
                            <th style="padding:6px;border:1px solid #ddd;text-align:left;">Product</th>
                            <th style="padding:6px;border:1px solid #ddd;text-align:center;">Qty</th>
                            <th style="padding:6px;border:1px solid #ddd;text-align:right;">Unit Price</th>
                            <th style="padding:6px;border:1px solid #ddd;text-align:right;">Subtotal</th>
                        </tr>
                    </thead>
                    <tbody>
                        {lines_html or "<tr><td colspan='4' style='padding:6px;border:1px solid #ddd'>No lines</td></tr>"}
                    </tbody>
                </table>

                <p style="margin-top: 14px;">
                    <a href="{order_link}" style="background:#875A7B;color:#fff;padding:8px 14px;text-decoration:none;border-radius:4px;display:inline-block;">
                        View Advance Order
                    </a>
                </p>
            </div>
        """

        mail_values = {
            "subject": _("Advance Payment Created: %s") % (self.name,),
            "body_html": body_html,
            "email_to": email_to,
            "email_from": self.env.user.email_formatted or self.env.company.email,
            "author_id": self.env.user.partner_id.id,
            "model": self._name,
            "res_id": self.id,
        }
        mail = self.env["mail.mail"].sudo().create(mail_values)
        mail.send()

    def _send_advance_notifications(self):
        """Send inbox notifications and emails to users configured on the Picking POS."""
        self.ensure_one()

        pickup_pos = self.pos_config_id
        if not pickup_pos:
            return

        notification_users = pickup_pos.advance_notification_user_ids
        if not notification_users:
            return

        partner = self.partner_id
        currency = self.currency_id

        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "http://localhost:8069")
        order_link = f"{base_url}/web#id={self.id}&model=pos.advance.order&view_type=form"

        email_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #007bff;">Advance Payment Created</h2>

            <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Advance Number:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{self.name}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Customer:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{partner.name}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Customer Phone:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{partner.phone or 'N/A'}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Invoice Total:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{currency.symbol} {self.amount_total:,.2f}</td>
                </tr>
                {"".join([
                    f"""
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Pledge Amount:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{currency.symbol} {self.pledge_amount:,.2f}</td>
                </tr>
                    """ if (self.pledge_amount) else ""
                ])}
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Advance Paid:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{currency.symbol} {self.advance_amount:,.2f}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Remaining Amount:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong style="color: #dc3545;">{currency.symbol} {self.amount_remaining:,.2f}</strong></td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Payment Method:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">
                        {(self.pos_payment_method_id.display_name if self.pos_payment_method_id else (self.payment_method or '').upper())}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Picking POS:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{pickup_pos.name}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Picking Date:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{self.picking_date.strftime('%Y-%m-%d %H:%M:%S') if self.picking_date else 'N/A'}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Created Date:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{self.create_date.strftime('%Y-%m-%d %H:%M:%S') if self.create_date else 'N/A'}</td>
                </tr>
            </table>

            <h3 style="margin-top: 30px; color: #28a745;">Products:</h3>
            <table style="width: 100%; border-collapse: collapse; margin-top: 10px;">
                <thead>
                    <tr style="background-color: #f8f9fa;">
                        <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Product</th>
                        <th style="padding: 10px; text-align: center; border: 1px solid #ddd;">Quantity</th>
                        <th style="padding: 10px; text-align: right; border: 1px solid #ddd;">Unit Price</th>
                        <th style="padding: 10px; text-align: right; border: 1px solid #ddd;">Subtotal</th>
                    </tr>
                </thead>
                <tbody>
        """

        for line in self.line_ids.filtered(lambda l: not l.display_type and l.product_id):
            email_body += f"""
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;">{line.product_id.display_name}</td>
                        <td style="padding: 8px; text-align: center; border: 1px solid #ddd;">{line.product_qty:g}</td>
                        <td style="padding: 8px; text-align: right; border: 1px solid #ddd;">{currency.symbol} {line.price_unit:,.2f}</td>
                        <td style="padding: 8px; text-align: right; border: 1px solid #ddd;">{currency.symbol} {line.price_subtotal_incl:,.2f}</td>
                    </tr>
            """

        email_body += f"""
                </tbody>
            </table>

            <p style="margin-top: 30px; color: #6c757d;">
                <a href="{order_link}"
                   style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">
                    View Advance Order
                </a>
            </p>
        </div>
        """

        parts = [
            f"Advance Payment Created: {self.name}",
            f"Customer: {partner.name}",
            f"Invoice Total: {currency.symbol} {self.amount_total:,.2f}",
        ]
        if self.pledge_amount:
            parts.append(f"Pledge: {currency.symbol} {self.pledge_amount:,.2f}")
        parts.extend([
            f"Advance Paid: {currency.symbol} {self.advance_amount:,.2f}",
            f"Remaining: {currency.symbol} {self.amount_remaining:,.2f}",
        ])
        notification_body = "\n".join(parts)

        message = self.message_post(
            body=notification_body,
            subject=f"Advance Payment Created: {self.name}",
            email_layout_xmlid="mail.mail_notification_light",
            subtype_xmlid="mail.mt_comment",
            mail_auto_delete=False,
        )

        partner_ids = [u.partner_id.id for u in notification_users if u.partner_id]
        if partner_ids:
            self.message_subscribe(partner_ids=partner_ids)

            msg_vals = {
                "partner_ids": partner_ids,
                "model": self._name,
                "res_id": self.id,
            }
            recipients_data = self._notify_get_recipients(message, msg_vals=msg_vals)
            notification_partner_ids = set(partner_ids)
            recipients_data = [r for r in recipients_data if r.get("id") in notification_partner_ids]
            for r in recipients_data:
                r["notif"] = "inbox"
            if recipients_data:
                self._notify_thread_by_inbox(message, recipients_data)

        for user in notification_users:
            try:
                email_to = user.email or user.partner_id.email
                if email_to:
                    mail_values = {
                        "subject": f"Advance Payment Created: {self.name}",
                        "body_html": email_body,
                        "email_to": email_to,
                        "email_from": self.env.user.email_formatted or self.env.company.email,
                        "author_id": self.env.user.partner_id.id,
                        "model": self._name,
                        "res_id": self.id,
                    }
                    mail = self.env["mail.mail"].sudo().create(mail_values)
                    mail.send()
            except Exception:
                pass

    def action_open_employee_pricelist_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Employee Authorization"),
            "res_model": "pos.advance.order.employee_pricelist.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_advance_order_id": self.id,
            },
        }

    @api.depends(
        "line_ids.price_subtotal_incl",
        "pledge_line_ids.pledge_subtotal",
        "discount_amount",
    )
    def _compute_amounts(self):
        for order in self:
            order.amount_products = sum(order.line_ids.mapped("price_subtotal_incl"))
            order.pledge_amount = sum(order.pledge_line_ids.mapped("pledge_subtotal"))

            total_after_discount = order.amount_products - (order.discount_amount or 0.0)

            order.amount_total = total_after_discount
            order.amount_grand_total = total_after_discount

    @api.depends("pledge_line_ids.pledge_qty")
    def _compute_pledge_count(self):
        for order in self:
            order.pledge_count = sum(order.pledge_line_ids.mapped("pledge_qty"))

    @api.depends("advance_pos_order_id.state", "remaining_pos_order_id.state")
    def _compute_payment_progress(self):
        for order in self:
            if order.remaining_pos_order_id and order.remaining_pos_order_id.state in ("paid", "done"):
                order.payment_progress = "fully_paid"
            elif order.advance_pos_order_id and order.advance_pos_order_id.state in ("paid", "done"):
                order.payment_progress = "advance_paid"
            else:
                order.payment_progress = "no_payment"

    def _sync_pledge_lines(self):
        """Keep pledge lines in sync with product lines.

        For each product in lines that has_pledge=True:
        - create/update a pledge line with pledge_qty = total product qty in the order
        - pledge_amount_unit = product template pledge_amount
        """
        for order in self:
            # Link pledge lines to the POS order which collected the pledge (remaining payment order)
            linked_pos_order_id = False
            if order.pledge_pos_order_id:
                linked_pos_order_id = order.pledge_pos_order_id.id

            # Aggregate qty by product for pledged products
            qty_by_product = {}
            amount_by_product = {}
            for line in order.line_ids.filtered(lambda l: not l.display_type and l.product_id):
                tmpl = line.product_id.product_tmpl_id
                if not getattr(tmpl, "has_pledge", False):
                    continue
                qty_by_product[line.product_id] = qty_by_product.get(line.product_id, 0.0) + (line.product_qty or 0.0)
                amount_by_product[line.product_id] = tmpl.pledge_amount or 0.0

            existing = {pl.product_id: pl for pl in order.pledge_line_ids}
            commands = []

            # Update/create current pledged products
            for product, qty in qty_by_product.items():
                unit_amount = amount_by_product.get(product, 0.0)
                if product in existing:
                    pl = existing[product]
                    commands.append(fields.Command.update(pl.id, {
                        "pledge_qty": qty,
                        "pledge_amount_unit": unit_amount,
                        "pos_order_id": linked_pos_order_id or False,
                    }))
                else:
                    commands.append(fields.Command.create({
                        "product_id": product.id,
                        "pledge_qty": qty,
                        "pledge_amount_unit": unit_amount,
                        "pos_order_id": linked_pos_order_id or False,
                        "partner_id": order.partner_id.id,
                    }))

            # Remove pledge lines for products that are no longer pledged in order lines
            for product, pl in existing.items():
                if product not in qty_by_product:
                    commands.append(fields.Command.delete(pl.id))

            if commands:
                order.write({"pledge_line_ids": commands})

    @api.depends("amount_grand_total", "advance_amount", "discount_amount", "state")
    def _compute_payment_amounts(self):
        for order in self:
            total = order.amount_grand_total or 0.0
            paid = max(order.advance_amount or 0.0, 0.0)

            if order.state == "fully_paid":
                order.amount_paid = total
                order.amount_remaining = 0.0
                continue

            order.amount_paid = min(paid, total)
            order.amount_remaining = total - order.amount_paid

    def _get_open_session(self, config):
        session = self.env["pos.session"].sudo().search(
            [("config_id", "=", config.id), ("state", "=", "opened"), ("rescue", "=", False)],
            limit=1,
        )
        if not session:
            raise UserError(_("No opened POS session found for %s. Please open a session first.") % config.display_name)
        return session

    def _get_pos_payment_method(self, session):
        self.ensure_one()
        methods = session.payment_method_ids
        if self.pos_payment_method_id:
            if self.pos_payment_method_id in methods:
                return self.pos_payment_method_id
            same_type = methods.filtered(
                lambda m: m.type == self.pos_payment_method_id.type
                and m.payment_method_type == "none"
            )[:1]
            if same_type:
                return same_type
        if self.payment_method == "cash":
            pm = methods.filtered(lambda m: m.type == "cash")[:1]
        else:
            pm = methods.filtered(lambda m: m.type == "bank")[:1]
        if not pm:
            raise UserError(_("No compatible POS payment method found on the opened session."))
        return pm

    def _resolve_remaining_payment_method(self, session, pos_payment_method_id=None):
        """POS payment method for completing advance: explicit choice from cashier, else advance order fallback."""
        self.ensure_one()
        if pos_payment_method_id:
            pm = self.env["pos.payment.method"].sudo().browse(int(pos_payment_method_id))
            if not pm.exists():
                raise UserError(_("Invalid POS payment method."))
            methods = session.payment_method_ids
            if pm.id not in methods.ids:
                raise UserError(_("This payment method is not available on the opened POS session."))
            if pm.type == "pay_later":
                raise UserError(_("Customer account payments cannot be used to complete advances."))
            if pm.payment_method_type and pm.payment_method_type != "none":
                raise UserError(
                    _("Integrated POS payment methods (terminal / QR) are not supported for completing advances.")
                )
            return pm
        return self._get_pos_payment_method(session)

    def _normalize_tax_ids(self, tax_value):
        """Normalize tax_ids input (either [Command/set], [(6,0,ids)], ids list) -> ids list."""
        if not tax_value:
            return []
        # XML/ORM commands like [(6,0,[1,2])]
        if isinstance(tax_value, list) and tax_value and isinstance(tax_value[0], (tuple, list)):
            cmd = tax_value[0]
            if len(cmd) >= 3 and cmd[0] == 6:
                return cmd[2] or []
            # Already in Command.* format or other commands; best effort
            ids = []
            for c in tax_value:
                if isinstance(c, (tuple, list)) and len(c) >= 3 and c[0] == 6:
                    ids.extend(c[2] or [])
            return ids
        # plain ids
        return tax_value if isinstance(tax_value, list) else []

    def _compute_pos_line_amounts(self, order, product, qty, price_unit, discount, tax_ids):
        """Compute tax excl/incl like POS does (fiscal position + compute_all)."""
        fpos = order.fiscal_position_id
        tax_ids = self.env["account.tax"].browse(tax_ids).filtered_domain(
            self.env["account.tax"]._check_company_domain(order.company_id)
        )
        taxes_to_apply = fpos.map_tax(tax_ids) if fpos else tax_ids
        price = price_unit * (1 - (discount or 0.0) / 100.0)
        if taxes_to_apply:
            res = taxes_to_apply.compute_all(
                price,
                order.currency_id,
                qty,
                product=product,
                partner=order.partner_id,
            )
            return res["total_excluded"], res["total_included"]
        # no taxes
        subtotal = price * qty
        return subtotal, subtotal

    def _create_pos_order(self, session, lines):
        """Create a backend POS order and its lines with required computed amounts."""
        self.ensure_one()
        order = self.env["pos.order"].sudo().create({
            "session_id": session.id,
            "partner_id": self.partner_id.id,
            "to_invoice": False,
            # Required monetary fields on pos.order are normally provided by the POS frontend.
            # When creating orders from backend code, we must initialize them then recompute.
            "amount_tax": 0.0,
            "amount_total": 0.0,
            "amount_paid": 0.0,
            "amount_return": 0.0,
            "amount_difference": 0.0,
            "is_advance_generated": True,
            "advance_order_id": self.id,
        })
        PosOrderLine = self.env["pos.order.line"].sudo()
        created_line_ids = []
        for spec in (lines or []):
            product = self.env["product.product"].browse(spec["product_id"])
            qty = spec.get("qty", 1.0)
            price_unit = spec.get("price_unit", 0.0)
            discount = spec.get("discount", 0.0)
            tax_ids = self._normalize_tax_ids(spec.get("tax_ids"))

            subtotal_excl, subtotal_incl = self._compute_pos_line_amounts(
                order=order,
                product=product,
                qty=qty,
                price_unit=price_unit,
                discount=discount,
                tax_ids=tax_ids,
            )

            created_line = PosOrderLine.create({
                "order_id": order.id,
                "product_id": product.id,
                "name": spec.get("name") or product.display_name,
                "qty": qty,
                "price_unit": price_unit,
                "discount": discount,
                "tax_ids": [Command.set(tax_ids)],
                "price_subtotal": subtotal_excl,
                "price_subtotal_incl": subtotal_incl,
                "price_extra": spec.get("price_extra", 0.0),
                "full_product_name": spec.get("full_product_name") or product.display_name,
            })
            created_line_ids.append(created_line.id)
        # Refresh the order record to ensure one2many lines are visible on this recordset
        # before computing totals (prevents stale-cache totals staying at 0.0).
        order = self.env["pos.order"].sudo().browse(order.id)
        order.invalidate_recordset(["lines", "amount_total", "amount_tax", "amount_paid", "amount_difference"])
        line_dump = [
            {
                "id": line.id,
                "product_id": line.product_id.id,
                "product_name": line.product_id.display_name,
                "qty": line.qty,
                "price_unit": line.price_unit,
                "discount": line.discount,
                "tax_ids": line.tax_ids.ids,
                "price_subtotal": line.price_subtotal,
                "price_subtotal_incl": line.price_subtotal_incl,
            }
            for line in order.lines
        ]
        base_lines = order.with_context(invoicing=True)._prepare_tax_base_line_values() or []
        base_line_dump = []
        for base_line in base_lines:
            tax_ids = (
                base_line.get("tax_ids").ids
                if getattr(base_line.get("tax_ids"), "ids", False) is not False
                else base_line.get("tax_ids")
            )
            base_line_dump.append(
                {
                    "record_id": base_line.get("id"),
                    "product_id": getattr(base_line.get("product_id"), "id", False),
                    "quantity": base_line.get("quantity"),
                    "price_unit": base_line.get("price_unit"),
                    "discount": base_line.get("discount"),
                    "tax_ids": tax_ids,
                    "sign": base_line.get("sign"),
                    "rate": base_line.get("rate"),
                    "special_mode": base_line.get("special_mode"),
                    "special_type": base_line.get("special_type"),
                }
            )
        _logger.info(
            "[ADV_POS_DEBUG] Pre-compute order id=%s advance_order=%s created_line_ids=%s line_dump=%s base_lines=%s",
            order.id,
            self.id,
            created_line_ids,
            line_dump,
            base_line_dump,
        )
        # `pos_settle_due` filters deposit/settle lines out of tax base lines unless
        # `invoicing` context is set. Advance flow relies on deposit-like products, so
        # compute prices with invoicing context to keep totals consistent.
        order.with_context(invoicing=True)._compute_prices()
        order.invalidate_recordset(["amount_total", "amount_tax", "amount_paid", "amount_difference"])
        _logger.info(
            "[ADV_POS_DEBUG] Post-compute order id=%s advance_order=%s amount_total=%s amount_tax=%s amount_paid=%s amount_difference=%s",
            order.id,
            self.id,
            order.amount_total,
            order.amount_tax,
            order.amount_paid,
            order.amount_difference,
        )
        return order

    def _pay_pos_order(self, order, payment_method, amount):
        """Create pos.payment and mark order as paid."""
        _logger.info(
            "[ADV_POS_DEBUG] Payment start order id=%s advance_order=%s payment_method=%s requested_amount=%s current_total=%s",
            order.id,
            self.id,
            payment_method.id,
            amount,
            order.amount_total,
        )
        self.env["pos.payment"].sudo().create({
            "pos_order_id": order.id,
            "amount": amount,
            "payment_method_id": payment_method.id,
        })
        order.with_context(invoicing=True)._compute_prices()
        order.action_pos_order_paid()
        order._create_order_picking()
        _logger.info(
            "[ADV_POS_DEBUG] Payment done order id=%s advance_order=%s state=%s amount_total=%s amount_paid=%s",
            order.id,
            self.id,
            order.state,
            order.amount_total,
            order.amount_paid,
        )
        return order

    @api.constrains("advance_amount")
    def _check_advance_amount(self):
        for order in self:
            if order.advance_amount and order.advance_amount < 0:
                raise UserError(_("Advance amount cannot be negative."))

    @api.constrains("pos_payment_method_id", "from_pos_config_id", "state")
    def _check_pos_payment_method_config(self):
        for order in self:
            if order.state != "draft" or not order.pos_payment_method_id or not order.from_pos_config_id:
                continue
            if order.pos_payment_method_id not in order.from_pos_config_id.payment_method_ids:
                raise UserError(_("The POS payment method must be enabled on the source (From) POS configuration."))

    @classmethod
    def _payment_method_selection_from_pos_pm(cls, pm):
        if not pm:
            return "cash"
        if pm.type == "cash":
            return "cash"
        return "bank"

    def action_confirm(self):
        for order in self:
            if order.state != "draft":
                continue

            discount = 0.0
            if order.discount_id:
                if order.discount_id.discount_type == "percent":
                    discount = order.amount_products * (order.discount_id.value / 100.0)
                else:
                    discount = order.discount_id.value

            order.discount_amount = max(
                0.0,
                min(discount, order.amount_products or 0.0)
            )

            order._compute_amounts()

            if order.advance_amount < 0:
                raise UserError(_("Advance amount cannot be negative."))

            if order.advance_amount > order.amount_grand_total:
                raise UserError(_("Advance amount cannot be greater than the total."))

            order.state = "confirmed"

        return True

    def action_set_to_draft(self):
        self.write({"state": "draft"})
        return True

    def action_cancel(self):
        self.write({"state": "cancel"})
        return True

    def unlink(self):
        # Business rule: Advance Orders must never be deleted (audit trail).
        raise UserError(_("You cannot delete Advance Orders. You can cancel them instead."))

    def write(self, vals):
        # Make cancelled advance orders fully read-only (server-side safety).
        for order in self:
            if order.state == "cancel":
                allowed = {"state"}
                if any(field_name not in allowed for field_name in vals.keys()):
                    raise UserError(_("You cannot modify a cancelled advance order."))
        if vals.get("pos_payment_method_id") and "payment_method" not in vals:
            pm = self.env["pos.payment.method"].browse(vals["pos_payment_method_id"])
            vals = dict(vals)
            vals["payment_method"] = self._payment_method_selection_from_pos_pm(pm)
        return super().write(vals)

    def _get_advance_pos_config(self):
        """POS config governing advance payment (deposit taken on From POS, else Picking POS)."""
        self.ensure_one()
        return self.from_pos_config_id or self.pos_config_id

    def _get_advance_receivable_account(self):
        """AR for advance reconciliation: POS setting if set, else partner property."""
        self.ensure_one()
        pos_cfg = self._get_advance_pos_config()
        return (
            pos_cfg.pos_advance_receivable_account_id
            or self.partner_id.with_company(self.company_id).property_account_receivable_id
        )

    def _get_payment_journal(self):
        """Select journal: POS payment method journal first (same as normal POS payments), then From/Picking POS fallback."""
        self.ensure_one()
        if self.pos_payment_method_id and self.pos_payment_method_id.journal_id:
            return self.pos_payment_method_id.journal_id
        pos_config = self.from_pos_config_id or self.pos_config_id
        if self.payment_method == "cash":
            journal = pos_config.pos_cash_journal_id
            if journal:
                return journal
            # Fallback: first cash payment method journal from POS config
            pm = pos_config.payment_method_ids.filtered(lambda m: m.type == "cash" and m.journal_id)[:1]
            return pm.journal_id
        # bank/card
        journal = pos_config.pos_card_journal_id
        if journal:
            return journal
        pm = pos_config.payment_method_ids.filtered(lambda m: m.type == "bank" and m.journal_id)[:1]
        return pm.journal_id

    def _get_inbound_payment_method_line(self, journal):
        # Prefer a method line that has an explicit outstanding/payment account.
        line = journal.inbound_payment_method_line_ids.filtered(lambda l: l.payment_account_id)[:1]
        if not line:
            line = journal.inbound_payment_method_line_ids[:1]
        if not line:
            raise UserError(_("Please define an inbound payment method on journal %s.") % journal.display_name)
        return line

    def _get_outbound_payment_method_line(self, journal):
        line = journal.outbound_payment_method_line_ids[:1]
        if not line:
            raise UserError(_("Please define an outbound payment method on journal %s.") % journal.display_name)
        return line

    def _create_advance_account_payment(self):
        """Create posted account.payment and transfer its receivable impact to liability."""
        self.ensure_one()
        pos_config = self._get_advance_pos_config()
        liability_account = pos_config.pos_advance_account_id
        _logger.info(
            "[ADV_RECON] Start advance account payment creation: advance=%s partner=%s amount=%s pos=%s from_pos=%s liability=%s",
            self.name,
            self.partner_id.id,
            self.advance_amount,
            self.pos_config_id.id,
            self.from_pos_config_id.id if self.from_pos_config_id else False,
            liability_account.id if liability_account else False,
        )
        if not liability_account:
            raise UserError(_("Please set 'POS Advance Account' on the POS configuration first."))

        journal = self._get_payment_journal()
        if not journal:
            raise UserError(_("Please configure a payment journal on the POS first."))
        payment_method_line = self._get_inbound_payment_method_line(journal)
        _logger.info(
            "[ADV_RECON] Using journal/payment method line: journal=%s method_line=%s",
            journal.id,
            payment_method_line.id,
        )

        payment = self.env["account.payment"].sudo().create({
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": self.partner_id.id,
            "amount": self.advance_amount,
            "currency_id": self.currency_id.id,
            "date": fields.Date.context_today(self),
            "journal_id": journal.id,
            "payment_method_line_id": payment_method_line.id,
            "memo": _("Advance Payment - %s") % self.name,
        })
        payment.action_post()
        _logger.info(
            "[ADV_RECON] account.payment posted: payment_id=%s move_id=%s state=%s method_line=%s method_line_account=%s",
            payment.id,
            payment.move_id.id if payment.move_id else False,
            payment.state,
            payment.payment_method_line_id.id if payment.payment_method_line_id else False,
            payment.payment_method_line_id.payment_account_id.id if payment.payment_method_line_id and payment.payment_method_line_id.payment_account_id else False,
        )
        if not payment.move_id:
            raise UserError(
                _(
                    "Advance account payment did not create a journal entry. "
                    "Please configure an inbound payment method/account on journal '%s'."
                )
                % (journal.display_name,)
            )

        receivable_account = self._get_advance_receivable_account()
        if not receivable_account:
            raise UserError(
                _(
                    "Please set 'POS Advance Receivable Account' on the POS configuration "
                    "or configure the customer's receivable account."
                )
            )
        _logger.info(
            "[ADV_RECON] receivable/liability accounts: receivable=%s liability=%s",
            receivable_account.id,
            liability_account.id,
        )

        transfer_move = self.env["account.move"].sudo().create({
            "journal_id": journal.id,
            "date": fields.Date.context_today(self),
            "ref": _("Advance Liability Transfer - %s") % self.name,
            "line_ids": [
                Command.create({
                    "name": _("Advance transfer %s") % self.name,
                    "account_id": receivable_account.id,
                    "partner_id": self.partner_id.id,
                    "debit": self.advance_amount,
                    "credit": 0.0,
                }),
                Command.create({
                    "name": _("Advance transfer %s") % self.name,
                    "account_id": liability_account.id,
                    "partner_id": self.partner_id.id,
                    "debit": 0.0,
                    "credit": self.advance_amount,
                }),
            ],
        })
        transfer_move.action_post()
        _logger.info(
            "[ADV_RECON] transfer move posted: move_id=%s line_ids=%s",
            transfer_move.id,
            transfer_move.line_ids.ids,
        )

        payment_receivable_lines = payment.move_id.line_ids.filtered(
            lambda l: l.account_id == receivable_account and not l.reconciled
        )
        transfer_receivable_lines = transfer_move.line_ids.filtered(
            lambda l: l.account_id == receivable_account and not l.reconciled
        )
        _logger.info(
            "[ADV_RECON] Pre-reconcile payment vs transfer: payment_lines=%s transfer_lines=%s payment_balances=%s transfer_balances=%s",
            payment_receivable_lines.ids,
            transfer_receivable_lines.ids,
            payment_receivable_lines.mapped("balance"),
            transfer_receivable_lines.mapped("balance"),
        )
        try:
            (payment_receivable_lines | transfer_receivable_lines).sudo().reconcile()
            _logger.info(
                "[ADV_RECON] Reconcile payment vs transfer done: payment_lines_reconciled=%s transfer_lines_reconciled=%s",
                payment_receivable_lines.mapped("reconciled"),
                transfer_receivable_lines.mapped("reconciled"),
            )
        except Exception as e:
            _logger.exception(
                "[ADV_RECON] Reconcile payment vs transfer failed: advance=%s payment_lines=%s transfer_lines=%s error=%s",
                self.name,
                payment_receivable_lines.ids,
                transfer_receivable_lines.ids,
                e,
            )
            raise

        self.advance_account_payment_id = payment.id
        self.advance_liability_move_id = transfer_move.id
        _logger.info(
            "[ADV_RECON] Advance payment flow complete: advance=%s payment_id=%s liability_move_id=%s",
            self.name,
            payment.id,
            transfer_move.id,
        )
        return payment

    def action_create_payment(self):
        for order in self:
            order.ensure_one()
            if order.state != "confirmed":
                raise UserError(_("You can only create a payment on a Confirmed advance order."))
            if order.advance_account_payment_id or order.advance_pos_order_id:
                raise UserError(_("A payment is already created for this advance order."))
            if not order.advance_amount or order.advance_amount <= 0:
                raise UserError(_("Advance amount must be greater than zero to create a payment."))

            # 1) Keep POS technical flow: create POS order + POS payment for advance.
            pos_config = order.from_pos_config_id or order.pos_config_id
            if not pos_config.advance_deposit_product_id:
                raise UserError(_("Please set 'Advance Deposit Product' on the POS configuration first."))

            session = order._get_open_session(pos_config)
            pm = order._get_pos_payment_method(session)

            deposit_product = pos_config.advance_deposit_product_id
            lines = [{
                "product_id": deposit_product.id,
                "qty": 1.0,
                "price_unit": order.advance_amount,
                "discount": 0.0,
                "tax_ids": [(6, 0, [])],
                "product_uom_id": deposit_product.uom_id.id,
                "name": order.name,
            }]
            pos_order = order._create_pos_order(session, lines)
            order._pay_pos_order(pos_order, pm, pos_order.amount_total)
            order.advance_pos_order_id = pos_order.id

            # 2) Additionally create account.payment + liability transfer for compliance flow.
            order._create_advance_account_payment()
            order.state = "advance_paid"
            _logger.info(
                "[ADV_RECON] action_create_payment completed: advance=%s state=%s pos_order=%s account_payment=%s",
                order.name,
                order.state,
                order.advance_pos_order_id.id if order.advance_pos_order_id else False,
                order.advance_account_payment_id.id if order.advance_account_payment_id else False,
            )
            # Notify manager on Picking POS
            order._send_create_payment_email_to_manager()
            # Notify configured users (inbox + email)
            order._send_advance_notifications()

        return True

    def action_create_remaining_payment(self, pos_payment_method_id=None):
        """After confirm:
        Create a POS sale order in the Picking POS session:
        - Products lines (income)
        - Advance reversal line (liability) as negative amount to clear the deposit
        Then register a pos.payment and mark the order paid.
        """
        for order in self:
            order.ensure_one()
            if order.state != "advance_paid":
                raise UserError(_("You can only create remaining payment after the advance is paid."))
            if not order.advance_account_payment_id and not order.advance_pos_order_id:
                raise UserError(_("Please create the advance payment first."))
            if order.remaining_pos_order_id:
                raise UserError(_("Remaining/reversal payments are already created for this order."))
            if order.pledge_pos_order_id:
                raise UserError(_("Pledge payment order is already created for this advance order."))
            if not order.amount_grand_total or order.amount_grand_total <= 0:
                raise UserError(_("Total amount must be greater than zero."))

            pos_config = order.pos_config_id
            if not pos_config.advance_deposit_product_id:
                raise UserError(_("Please set 'Advance Deposit Product' on the Picking POS configuration first."))

            session = order._get_open_session(pos_config)
            pm = order._resolve_remaining_payment_method(session, pos_payment_method_id)

            # Build POS order lines
            lines = []
            for l in order.line_ids.filtered(lambda x: not x.display_type and x.product_id):
                lines.append({
                    "product_id": l.product_id.id,
                    "qty": l.product_qty,
                    "price_unit": l.price_unit,
                    "discount": 0.0,
                    "tax_ids": [(6, 0, l.product_id.taxes_id.ids)],
                    "product_uom_id": l.product_uom_id.id,
                    "name": l.product_id.display_name,
                })

            # Apply advance as negative liability line
            if order.advance_amount and order.advance_amount > 0:
                deposit_product = pos_config.advance_deposit_product_id
                lines.append({
                    "product_id": deposit_product.id,
                    "qty": 1.0,
                    "price_unit": -order.advance_amount,
                    "discount": 0.0,
                    "tax_ids": [(6, 0, [])],
                    "product_uom_id": deposit_product.uom_id.id,
                    "name": _("Advance"),
                })

            pos_order = order._create_pos_order(session, lines)
            order._pay_pos_order(pos_order, pm, pos_order.amount_total)
            order.remaining_pos_order_id = pos_order.id
            order.state = "fully_paid"

            # Create a separate POS order for pledge (paid immediately) in the same session
            if order.pledge_amount and order.pledge_amount > 0 and pos_config.pledge_product_id:
                pledge_product = pos_config.pledge_product_id
                pledge_lines = [{
                    "product_id": pledge_product.id,
                    "qty": 1.0,
                    "price_unit": order.pledge_amount,
                    "discount": 0.0,
                    "tax_ids": [(6, 0, [])],
                    "product_uom_id": pledge_product.uom_id.id,
                    "name": _("Pledge"),
                }]
                pledge_order = order._create_pos_order(session, pledge_lines)
                order._pay_pos_order(pledge_order, pm, pledge_order.amount_total)
                order.pledge_pos_order_id = pledge_order.id
                # Link pledge lines to the POS order that collected the pledge.
                if order.pledge_line_ids:
                    order.pledge_line_ids.sudo().write({
                        "pos_order_id": pledge_order.id,
                        "partner_id": order.partner_id.id,
                    })

        return True

    def action_create_remaining_amount(self, pos_payment_method_id=None):
        """Alias for POS button flow."""
        return self.action_create_remaining_payment(pos_payment_method_id=pos_payment_method_id)

    def action_refund_advance_payment(self):
        for order in self:
            order.ensure_one()
            if not order.advance_pos_order_id:
                raise UserError(_("Please create the advance payment first."))
            if order.refund_advance_pos_order_id:
                raise UserError(_("Advance refund payment is already created for this order."))

            pos_config = order.from_pos_config_id or order.pos_config_id
            if not pos_config.advance_deposit_product_id:
                raise UserError(_("Please set 'Advance Deposit Product' on the POS configuration first."))

            session = order._get_open_session(pos_config)
            pm = order._get_pos_payment_method(session)

            deposit_product = pos_config.advance_deposit_product_id
            lines = [{
                "product_id": deposit_product.id,
                "qty": -1.0,
                "price_unit": order.advance_amount,
                "discount": 0.0,
                "tax_ids": [(6, 0, [])],
                "product_uom_id": deposit_product.uom_id.id,
                "name": _("Refund Advance"),
            }]
            pos_order = order._create_pos_order(session, lines)
            order._pay_pos_order(pos_order, pm, pos_order.amount_total)
            order.refund_advance_pos_order_id = pos_order.id
            order.state = "cancel"

        return True

    def action_print_receipt(self):
        self.ensure_one()
        return self.env.ref("pos_advance_order.action_report_pos_advance_order_receipt").report_action(self)

    def action_print_full_receipt(self):
        self.ensure_one()
        return self.env.ref("pos_advance_order.action_report_pos_advance_order_full_receipt").report_action(self)

    def action_return_pledge(self):
        for order in self:
            order.ensure_one()
            if order.return_pledge_pos_order_id:
                raise UserError(_("Pledge return payment is already created."))
            if not order.pledge_amount or order.pledge_amount <= 0:
                raise UserError(_("No pledge amount to return."))

            pledge_collection_order = order.pledge_line_ids.filtered(lambda pl: pl.pos_order_id)[:1].pos_order_id
            if not pledge_collection_order:
                raise UserError(_("Pledge was not collected yet on a POS order, so it cannot be returned."))

            pos_config = pledge_collection_order.config_id or pledge_collection_order.session_id.config_id
            if not pos_config.pledge_product_id:
                raise UserError(_("Please set 'Pledge Product' on the POS configuration first."))

            session = order._get_open_session(pos_config)
            pm = order._get_pos_payment_method(session)
            pledge_product = pos_config.pledge_product_id
            lines = [{
                "product_id": pledge_product.id,
                "qty": -1.0,
                "price_unit": order.pledge_amount,
                "discount": 0.0,
                "tax_ids": [(6, 0, [])],
                "product_uom_id": pledge_product.uom_id.id,
                "name": _("Return Pledge"),
            }]
            pos_order = order._create_pos_order(session, lines)
            order._pay_pos_order(pos_order, pm, pos_order.amount_total)
            order.return_pledge_pos_order_id = pos_order.id

        return True

    @api.model_create_multi
    def create(self, vals_list):
        PaymentMethod = self.env["pos.payment.method"]
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("pos.advance.order") or _("New")
            if vals.get("pos_payment_method_id") and "payment_method" not in vals:
                pm = PaymentMethod.browse(vals["pos_payment_method_id"])
                vals["payment_method"] = self._payment_method_selection_from_pos_pm(pm)
        return super().create(vals_list)

    # -------------------------------------------------------------------------
    # Catalog integration (product.catalog.mixin)
    # -------------------------------------------------------------------------

    def _is_readonly(self):
        self.ensure_one()
        return self.state != "draft"

    def _get_action_add_from_catalog_extra_context(self):
        self.ensure_one()
        return {
            **super()._get_action_add_from_catalog_extra_context(),
            "product_catalog_currency_id": self.currency_id.id,
            "product_catalog_digits": self.line_ids._fields["price_unit"].get_digits(self.env),
            "show_sections": False,
        }

    def _get_product_catalog_domain(self) -> Domain:
        return super()._get_product_catalog_domain() & Domain("available_in_pos", "=", True)

    def _get_product_catalog_order_data(self, products, **kwargs):
        res = super()._get_product_catalog_order_data(products, **kwargs)
        pricelist = self._get_effective_pricelist()
        if pricelist:
            price_map = pricelist._get_products_price(
                quantity=1.0,
                products=products,
                currency=self.currency_id,
                date=self.picking_date,
                **kwargs,
            )
            for product in products:
                res[product.id]["price"] = price_map.get(product.id, product.lst_price)
        else:
            for product in products:
                res[product.id]["price"] = product.lst_price
        return res

    def _get_product_catalog_record_lines(self, product_ids, child_field=False, **kwargs):
        self.ensure_one()
        child_field = child_field or "line_ids"
        grouped_lines = {}
        for line in self[child_field].filtered(lambda l: l.product_id and l.product_id.id in product_ids and not l.display_type):
            grouped_lines.setdefault(line.product_id, self.env["pos.advance.order.line"])
            grouped_lines[line.product_id] |= line
        return grouped_lines

    def _update_order_line_info(self, product_id, quantity, *, child_field="line_ids", **kwargs):
        self.ensure_one()
        child_field = child_field or "line_ids"
        lines = self[child_field].filtered(lambda l: l.product_id.id == product_id and not l.display_type)
        product = self.env["product.product"].browse(product_id)

        pricelist = self._get_effective_pricelist()
        product_price = (
            pricelist._get_product_price(
                product=product,
                quantity=max(quantity or 1.0, 1.0),
                currency=self.currency_id,
                date=self.picking_date,
                **kwargs,
            )
            if pricelist
            else product.lst_price
        )

        if lines:
            line = lines[0]
            if quantity and quantity > 0:
                line.product_qty = quantity
                line.price_unit = product_price
                return line.price_unit
            # quantity == 0 -> remove the line (draft only)
            if self.state == "draft":
                price = line.price_unit
                line.unlink()
                return price
            line.product_qty = 0
            return line.price_unit

        if quantity and quantity > 0:
            line = self.env["pos.advance.order.line"].create({
                "order_id": self.id,
                "product_id": product_id,
                "product_qty": quantity,
                "price_unit": product_price,
            })
            return line.price_unit

        # quantity of 0, no line to update -> return default product price for catalog display
        return product_price


class PosAdvanceOrderLine(models.Model):
    _name = "pos.advance.order.line"
    _description = "POS Advance Order Line"
    _order = "sequence, id"

    order_id = fields.Many2one("pos.advance.order", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)

    display_type = fields.Selection(
        [
            ("line_section", "Section"),
            ("line_note", "Note"),
        ],
        default=False,
    )

    product_id = fields.Many2one(
        "product.product",
        string="Product",
        domain=[("available_in_pos", "=", True)],
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        related="product_id.uom_id",
        store=True,
        readonly=True,
    )
    product_qty = fields.Float(string="Quantity", default=1.0)
    price_unit = fields.Float(string="Unit Price", digits="Product Price")

    currency_id = fields.Many2one("res.currency", related="order_id.currency_id", store=True, readonly=True)
    tax_ids = fields.Many2many(
        "account.tax",
        string="Taxes",
        domain=lambda self: self.env["account.tax"]._check_company_domain(self.env.company),
    )
    price_subtotal = fields.Monetary(
        string="Tax Excl.",
        currency_field="currency_id",
        compute="_compute_price_subtotal",
        store=True,
    )
    price_subtotal_incl = fields.Monetary(
        string="Tax Incl.",
        currency_field="currency_id",
        compute="_compute_price_subtotal",
        store=True,
    )

    @api.depends("product_qty", "price_unit", "tax_ids")
    def _compute_price_subtotal(self):
        for line in self:
            if line.display_type:
                line.price_subtotal = 0
                line.price_subtotal_incl = 0
            else:
                qty = line.product_qty or 0.0
                price = line.price_unit or 0.0
                if line.tax_ids:
                    taxes = line.tax_ids.compute_all(
                        price,
                        line.order_id.currency_id,
                        qty,
                        product=line.product_id,
                        partner=line.order_id.partner_id,
                    )
                    line.price_subtotal = taxes["total_excluded"]
                    line.price_subtotal_incl = taxes["total_included"]
                else:
                    line.price_subtotal = qty * price
                    line.price_subtotal_incl = qty * price

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            if not line.product_id:
                return
            # Default taxes from product (company filtered)
            line.tax_ids = line.product_id.taxes_id.filtered_domain(
                self.env["account.tax"]._check_company_domain(line.order_id.company_id if line.order_id else self.env.company)
            )
            if not line.price_unit:
                order = line.order_id
                pricelist = order._get_effective_pricelist() if order else False
                line.price_unit = (
                    pricelist._get_product_price(
                        product=line.product_id,
                        quantity=max(line.product_qty or 1.0, 1.0),
                        currency=order.currency_id,
                        uom=line.product_uom_id,
                        date=order.picking_date,
                    )
                    if pricelist and order and order.currency_id
                    else line.product_id.lst_price
                )

    @api.ondelete(at_uninstall=False)
    def _unlink_except_when_order_not_draft(self):
        for line in self:
            if line.order_id and line.order_id.state != "draft":
                raise UserError(_("You can only delete lines on a Draft advance order."))

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.mapped("order_id")._sync_pledge_lines()
        return lines

    def write(self, vals):
        res = super().write(vals)
        self.mapped("order_id")._sync_pledge_lines()
        return res

    def unlink(self):
        orders = self.mapped("order_id")
        res = super().unlink()
        orders._sync_pledge_lines()
        return res

    @api.readonly
    def action_add_from_catalog(self):
        order = self.env["pos.advance.order"].browse(self.env.context.get("order_id"))
        return order.with_context(child_field="line_ids").action_add_from_catalog()

    def _get_product_catalog_lines_data(self, parent_record=False, **kwargs):
        """Provide catalog info for this order's lines (quantity, price, readOnly, uom)."""
        if len(self) == 1:
            return {
                "quantity": self.product_qty,
                "price": self.price_unit,
                "readOnly": self.order_id._is_readonly(),
                "uomDisplayName": self.product_uom_id.display_name or self.product_id.uom_id.display_name,
            }
        elif self:
            self.product_id.ensure_one()
            order = self[0].order_id
            return {
                "readOnly": True,
                "price": self[0].price_unit or self.product_id.lst_price,
                "quantity": sum(self.mapped("product_qty")),
                "uomDisplayName": self.product_id.uom_id.display_name,
            }
        return {"quantity": 0}

