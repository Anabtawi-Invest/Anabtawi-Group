# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import email_normalize


class PortalVanUserCreate(models.TransientModel):
    _name = "portal.van.user.create"
    _description = "Create Van Portal User"

    name = fields.Char(string="Van / User Name", required=True)
    login = fields.Char(
        string="Login / Email",
        required=True,
        help="Used as portal login. Warehouse short code is derived from this.",
    )
    phone = fields.Char(string="Phone")
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    password = fields.Char(
        string="Password",
        help="Optional. Leave empty to set later or send a portal invitation email.",
    )
    send_invitation = fields.Boolean(
        string="Send Invitation Email",
        default=False,
        help="Send the standard portal set-password invitation email.",
    )
    van_customer_id = fields.Many2one(
        "res.partner",
        string="Van Customer",
        help="Fixed commercial customer for this van. Portal sales use this partner; "
        "delivery addresses are created under it. Set the contact's Pricelist "
        "(Sales & Purchase) for sale prices and transfer product filtering.",
    )
    van_payment_journal_id = fields.Many2one(
        "account.journal",
        string="Payment Journal",
        required=True,
        domain="[('type', 'in', ('cash', 'bank')), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Cash/bank journal used to fully pay portal sale invoices for this van.",
    )
    van_source_location_id = fields.Many2one(
        "stock.location",
        string="Default Source Location",
        required=True,
        domain="[('usage', '=', 'internal'), ('active', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Default Source on portal Create Internal Transfer for this van.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env["res.company"].browse(res.get("company_id")) or self.env.company
        if company and (
            "van_source_location_id" in fields_list or not fields_list
        ):
            location = self._default_source_for_company(company)
            if location:
                res["van_source_location_id"] = location.id
        return res

    def _default_source_for_company(self, company):
        if not company:
            return self.env["stock.location"]
        user = self.env.user.sudo()
        if hasattr(user, "_van_get_supplier_warehouse"):
            supplier = user._van_get_supplier_warehouse(company)
            location = supplier.lot_stock_id if supplier else self.env["stock.location"]
            if location and location.usage == "internal" and location.active:
                return location
        warehouse = (
            self.env["stock.warehouse"]
            .sudo()
            .search([("company_id", "=", company.id)], order="id asc", limit=1)
        )
        location = warehouse.lot_stock_id if warehouse else self.env["stock.location"]
        if location and location.usage == "internal" and location.active:
            return location
        return self.env["stock.location"]

    @api.onchange("company_id")
    def _onchange_company_id_source(self):
        self.van_source_location_id = self._default_source_for_company(self.company_id)

    @api.constrains("login")
    def _check_login(self):
        for wiz in self:
            login = (wiz.login or "").strip()
            if not login:
                raise ValidationError(_("Login / Email is required."))
            if self.env["res.users"].sudo().with_context(active_test=False).search_count(
                [("login", "=", login)], limit=1
            ):
                raise ValidationError(_("A user with login %s already exists.") % login)

    def action_create(self):
        self.ensure_one()
        company = self.company_id
        if not company:
            raise UserError(_("Please select a company."))
        if not self.van_source_location_id:
            raise UserError(_("Please select a Default Source Location."))
        source = self.van_source_location_id
        if source.usage != "internal" or not source.active:
            raise UserError(
                _("Default Source Location must be an active internal location.")
            )
        if source.company_id and source.company_id != company:
            raise UserError(
                _("Default Source Location must belong to company %s.")
                % company.display_name
            )

        Warehouse = self.env["stock.warehouse"].sudo()
        if not Warehouse.search_count([("company_id", "=", company.id)], limit=1):
            raise UserError(
                _(
                    "No warehouse exists in company %s. "
                    "Create the main warehouse first."
                )
                % company.display_name
            )

        login = (self.login or "").strip()
        email = email_normalize(login) or login
        name = (self.name or "").strip()

        partner = (
            self.env["res.partner"]
            .sudo()
            .with_company(company)
            .create(
                {
                    "name": name,
                    "email": email,
                    "phone": self.phone or False,
                    "company_id": company.id,
                }
            )
        )

        Users = self.env["res.users"].sudo().with_context(no_reset_password=True)
        try:
            user = Users.with_company(company)._create_user_from_template(
                {
                    "name": name,
                    "login": login,
                    "email": email,
                    "partner_id": partner.id,
                    "company_id": company.id,
                    "company_ids": [(6, 0, [company.id])],
                }
            )
        except Exception as err:
            raise UserError(_("Could not create portal user: %s") % err) from err

        group_portal = self.env.ref("base.group_portal")
        group_public = self.env.ref("base.group_public", raise_if_not_found=False)
        group_cmds = [(4, group_portal.id)]
        if group_public:
            group_cmds.append((3, group_public.id))
        user_vals = {
            "active": True,
            "company_id": company.id,
            "company_ids": [(6, 0, [company.id])],
            "group_ids": group_cmds,
            "van_source_location_id": source.id,
        }
        if self.van_customer_id:
            user_vals["van_customer_id"] = self.van_customer_id.id
        if self.van_payment_journal_id:
            user_vals["van_payment_journal_id"] = self.van_payment_journal_id.id
        user.write(user_vals)

        if self.password:
            user._change_password(self.password)

        user._create_van_stock_configuration()

        if self.send_invitation:
            self._send_portal_invitation(user)

        message = _(
            "Van portal user created.\n"
            "User: %(user)s\n"
            "Warehouse: %(wh)s\n"
            "Transit: %(transit)s\n"
            "Stock: %(stock)s\n"
            "Source: %(source)s"
        ) % {
            "user": user.login,
            "wh": user.van_warehouse_id.display_name,
            "transit": user.van_transit_location_id.display_name,
            "stock": user.van_warehouse_id.lot_stock_id.display_name,
            "source": user.van_source_location_id.display_name,
        }
        return {
            "type": "ir.actions.act_window",
            "name": _("Van Portal User"),
            "res_model": "res.users",
            "res_id": user.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
            "context": {"form_view_initial_mode": "readonly"},
            "effect": {
                "fadeout": "slow",
                "message": message,
                "type": "rainbow_man",
            },
        }

    def _send_portal_invitation(self, user):
        template = self.env.ref(
            "auth_signup.portal_set_password_email",
            raise_if_not_found=False,
        )
        if not template:
            raise UserError(
                _("Portal invitation email template was not found.")
            )
        partner = user.partner_id.sudo()
        partner.signup_prepare()
        template.sudo().send_mail(user.id, force_send=True)
