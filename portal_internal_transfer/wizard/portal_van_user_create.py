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
        user.write(
            {
                "active": True,
                "company_id": company.id,
                "company_ids": [(6, 0, [company.id])],
                "group_ids": group_cmds,
            }
        )

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
            "Stock: %(stock)s"
        ) % {
            "user": user.login,
            "wh": user.van_warehouse_id.display_name,
            "transit": user.van_transit_location_id.display_name,
            "stock": user.van_warehouse_id.lot_stock_id.display_name,
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
