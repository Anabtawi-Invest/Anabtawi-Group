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
    is_employee_discount = fields.Boolean(
        string="Employee Discount",
        default=False,
        help="If enabled, this discount can be authorized by a selected employee password or the configured manager password.",
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
                # keep it aligned with the POS behavior (0..100)
                raise ValidationError(_("Discount must be between 0 and 100."))

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [("pos_config_id", "=", config.id), ("active", "=", True)]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["id", "name", "discount", "sequence", "pos_config_id", "is_employee_discount"]

    @api.model
    def pos_validate_discount_authorization(self, discount_id, password, employee_id=False):
        discount = self.sudo().browse(int(discount_id or 0)).exists()
        if not discount:
            raise UserError(_("Invalid predefined discount."))

        password = str(password or "").strip()
        if not password:
            raise UserError(_("Password is required."))

        manager_user = discount.pos_config_id.advance_order_manager_id
        manager_employee = manager_user.employee_id if manager_user else False
        hr_employee_model = self.env["hr.employee"]

        manager_valid = bool(
            manager_employee
            and hr_employee_model.pos_employee_request_check_password(manager_employee.id, password)
        )

        employee_valid = False
        if discount.is_employee_discount and employee_id:
            employee = hr_employee_model.sudo().browse(int(employee_id)).exists()
            employee_valid = bool(
                employee and hr_employee_model.pos_employee_request_check_password(employee.id, password)
            )

        if manager_valid or employee_valid:
            _logger.debug(
                "POS predefined discount auth OK: discount_id=%s manager_valid=%s employee_valid=%s",
                discount.id,
                manager_valid,
                employee_valid,
            )
            return {
                "authorized": True,
                "manager_override": manager_valid,
                "employee_authorized": employee_valid,
            }

        _logger.warning(
            "POS predefined discount auth FAILED: discount_id=%s pos_config=%s "
            "manager_user=%s (%s) manager_employee=%s (%s) "
            "is_employee_discount=%s selected_employee_id=%s pw_len=%s pw_isdigit=%s "
            "manager_valid=%s employee_valid=%s (details: preceding POS employee password check logs)",
            discount.id,
            discount.pos_config_id.id,
            manager_user.id if manager_user else None,
            manager_user.login if manager_user else None,
            manager_employee.id if manager_employee else None,
            manager_employee.name if manager_employee else None,
            discount.is_employee_discount,
            employee_id or None,
            len(password),
            password.isdigit(),
            manager_valid,
            employee_valid,
        )

        if discount.is_employee_discount:
            raise UserError(
                _(
                    "Authorization failed. Enter the selected employee password or the manager password."
                )
            )

        if not manager_employee:
            raise UserError(_("Please configure an Advance Orders Manager with an employee record on this POS."))

        raise UserError(_("Authorization failed. Enter the manager password to apply this discount."))


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

