# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PosPredefinedDiscount(models.Model):
    _name = "pos.predefined.discount"
    _description = "POS Predefined Discount"
    _order = "sequence, id"
    _inherit = ["pos.load.mixin"]

    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    name = fields.Char(required=True)
    discount = fields.Float(string="Discount (%)", required=True, default=0.0)
    allowed_for_employee = fields.Boolean(
        string="Allowed for Employee",
        default=False,
        help="If enabled, this discount is available in the POS Employee Discount button "
             "and must be authorized with the selected employee's OTP.",
    )
    pos_config_id = fields.Many2one(
        "pos.config",
        required=True,
        ondelete="cascade",
        index=True,
    )

    @api.constrains("discount")
    def _check_discount_range(self):
        for rec in self:
            if rec.discount < 0.0 or rec.discount > 100.0:
                raise ValidationError(_("Discount must be between 0 and 100."))

    @api.model
    def _pos_discount_employee_password_matches(self, employee, password):
        """Validate employee OTP (digits + match + expiry) via employee_request."""
        if not employee:
            return False
        return bool(
            self.env["hr.employee"].sudo().pos_employee_request_check_password(
                employee.id, password
            )
        )

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [("pos_config_id", "=", config.id), ("active", "=", True)]

    @api.model
    def _load_pos_data_fields(self, config):
        return [
            "id",
            "name",
            "discount",
            "sequence",
            "pos_config_id",
            "allowed_for_employee",
        ]

    @api.model
    def pos_get_employee_partners(self, config_id=False, search=False, limit=200):
        """Return employee partners for the POS picker.

        Rows are keyed by partner id (for setting the POS customer), but the
        displayed name is the employee name. Search matches employee name,
        barcode, and linked partner name.
        """
        Employee = self.env["hr.employee"].sudo()
        domain = [
            ("active", "=", True),
            "|",
            ("work_contact_id", "!=", False),
            ("user_partner_id", "!=", False),
        ]
        if config_id:
            config = self.env["pos.config"].sudo().browse(int(config_id)).exists()
            if config and config.company_id:
                domain = [
                    "|",
                    ("company_id", "=", False),
                    ("company_id", "=", config.company_id.id),
                ] + domain

        search = str(search or "").strip()
        if search:
            domain += [
                "|",
                "|",
                "|",
                ("name", "ilike", search),
                ("barcode", "ilike", search),
                ("work_contact_id.name", "ilike", search),
                ("user_partner_id.name", "ilike", search),
            ]

        employees = Employee.search(domain, order="name", limit=int(limit or 200))
        result = []
        seen_partner_ids = set()
        for employee in employees:
            partner = employee.work_contact_id or employee.user_partner_id
            if not partner or partner.id in seen_partner_ids:
                continue
            seen_partner_ids.add(partner.id)
            result.append(
                {
                    "id": partner.id,
                    "name": employee.name,
                    "partner_name": partner.name,
                    "barcode": employee.barcode or partner.barcode or "",
                    "employee_id": employee.id,
                }
            )
        return result

    @api.model
    def _employee_for_partner(self, partner, company=False):
        if not partner:
            return self.env["hr.employee"]
        Employee = self.env["hr.employee"].sudo()
        domain = [
            "|",
            ("work_contact_id", "=", partner.id),
            ("user_partner_id", "=", partner.id),
        ]
        if company:
            domain = [("company_id", "=", company.id)] + domain
        return Employee.search(domain, limit=1)

    @api.model
    def pos_validate_discount_authorization(self, discount_id, password, employee_id=False):
        """Manager authorization for the regular Discount button (non-employee discounts)."""
        discount = self.sudo().browse(int(discount_id or 0)).exists()
        if not discount:
            raise UserError(_("Invalid predefined discount."))
        if discount.allowed_for_employee:
            raise UserError(
                _("This discount is reserved for Employee Discount. Use the Employee Discount button.")
            )

        password = str(password or "").strip()
        if not password:
            raise UserError(_("Password is required."))

        manager_user = discount.pos_config_id.advance_order_manager_id
        manager_employee = manager_user.employee_id if manager_user else False
        if not manager_employee:
            raise UserError(
                _("Please configure an Advance Orders Manager with an employee record on this POS.")
            )

        if self._pos_discount_employee_password_matches(manager_employee, password):
            return {
                "authorized": True,
                "manager_override": True,
                "employee_authorized": False,
            }

        _logger.warning(
            "POS predefined discount auth FAILED (manager): discount_id=%s pos_config=%s",
            discount.id,
            discount.pos_config_id.id,
        )
        raise UserError(_("Authorization failed. Enter the manager password to apply this discount."))

    @api.model
    def pos_validate_employee_discount_authorization(self, discount_id, partner_id, password):
        """Employee-only OTP authorization for the Employee Discount button."""
        discount = self.sudo().browse(int(discount_id or 0)).exists()
        if not discount:
            raise UserError(_("Invalid predefined discount."))
        if not discount.allowed_for_employee:
            raise UserError(_("This discount is not allowed for employees."))

        partner = self.env["res.partner"].sudo().browse(int(partner_id or 0)).exists()
        if not partner:
            raise UserError(_("Please select an employee customer."))

        password = str(password or "").strip()
        if not password:
            raise UserError(_("OTP is required."))

        company = discount.pos_config_id.company_id
        employee = self._employee_for_partner(partner, company=company)
        if not employee:
            raise UserError(_("No employee is linked to the selected customer."))

        if not self._pos_discount_employee_password_matches(employee, password):
            _logger.warning(
                "POS employee discount auth FAILED: discount_id=%s partner_id=%s employee_id=%s",
                discount.id,
                partner.id,
                employee.id,
            )
            raise UserError(_("Authorization failed. Employee OTP does not match."))

        return {
            "authorized": True,
            "partner_id": partner.id,
            "employee_id": employee.id,
            "discount": discount.discount,
        }


class PosConfig(models.Model):
    _inherit = "pos.config"

    predefined_discount_ids = fields.One2many(
        "pos.predefined.discount",
        "pos_config_id",
        string="Predefined Discounts",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_predefined_discount_ids = fields.One2many(
        related="pos_config_id.predefined_discount_ids",
        readonly=False,
    )
