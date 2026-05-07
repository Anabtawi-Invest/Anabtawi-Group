# -*- coding: utf-8 -*-

import logging

from odoo import api, models, Command
from odoo.tools import email_normalize

_logger = logging.getLogger(__name__)

# Default portal password (requested). Weak for production — change after first login or in code.
PORTAL_DEFAULT_PASSWORD = "123"


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def _hr_auto_portal_get_login_email(self):
        self.ensure_one()
        email = (self.work_contact_id.email or self.work_email or "").strip()
        normalized = email_normalize(email) if email else ""
        return normalized or ""

    def _hr_auto_portal_link_user(self, user):
        """Link user through hr.employee (not only resource) so the UI and constraints stay consistent."""
        self.ensure_one()
        self.env.flush_all()
        self.sudo().write({"user_id": user.id})
        _logger.info(
            "hr_employee_auto_portal: linked employee id=%s (%s) to user id=%s login=%s",
            self.id,
            self.name,
            user.id,
            user.login,
        )

    def _hr_auto_portal_create_user(self):
        """Create one portal user per eligible employee and link via user_id (official hr path)."""
        portal_group = self.env.ref("base.group_portal", raise_if_not_found=False)
        if not portal_group:
            _logger.warning(
                "hr_employee_auto_portal: abort — base.group_portal missing (install Portal app)."
            )
            return

        Users = self.env["res.users"].sudo()
        employees = self.sudo()
        _logger.info(
            "hr_employee_auto_portal: run for %s employee(s) ids=%s",
            len(employees),
            employees.ids,
        )

        for employee in employees:
            if employee.user_id:
                _logger.info(
                    "hr_employee_auto_portal: skip employee id=%s (%s) — already has user_id=%s (%s)",
                    employee.id,
                    employee.name,
                    employee.user_id.id,
                    employee.user_id.login,
                )
                continue
            partner = employee.work_contact_id
            if not partner:
                _logger.info(
                    "hr_employee_auto_portal: skip employee id=%s (%s) — no work_contact_id",
                    employee.id,
                    employee.name,
                )
                continue
            login = employee._hr_auto_portal_get_login_email()
            if not login:
                _logger.info(
                    "hr_employee_auto_portal: skip employee id=%s (%s) — no usable work email "
                    "(work_email=%r work_contact.email=%r)",
                    employee.id,
                    employee.name,
                    employee.work_email,
                    partner.email,
                )
                continue
            if partner.email != login:
                partner.write({"email": login})

            existing_login = Users.with_context(active_test=False).search(
                [("login", "=", login)], limit=1
            )
            if existing_login:
                _logger.info(
                    "hr_employee_auto_portal: skip employee id=%s (%s) — login %r already taken by user id=%s",
                    employee.id,
                    employee.name,
                    login,
                    existing_login.id,
                )
                continue
            if partner.user_ids:
                portal_user = partner.user_ids.filtered(
                    lambda u: u.sudo().has_group("base.group_portal")
                )[:1]
                if portal_user:
                    _logger.info(
                        "hr_employee_auto_portal: employee id=%s (%s) — partner id=%s already has portal user id=%s, linking",
                        employee.id,
                        employee.name,
                        partner.id,
                        portal_user.id,
                    )
                    employee._hr_auto_portal_link_user(portal_user)
                else:
                    other = partner.user_ids
                    _logger.info(
                        "hr_employee_auto_portal: skip employee id=%s (%s) — partner id=%s linked to "
                        "%s non-portal user(s) ids=%s logins=%s",
                        employee.id,
                        employee.name,
                        partner.id,
                        len(other),
                        other.ids,
                        other.mapped("login"),
                    )
                continue

            user = Users.create(
                {
                    "name": employee.name,
                    "login": login,
                    "password": PORTAL_DEFAULT_PASSWORD,
                    "partner_id": partner.id,
                    "company_id": employee.company_id.id,
                    "company_ids": [Command.set([employee.company_id.id])],
                    "group_ids": [Command.set([portal_group.id])],
                }
            )
            employee._hr_auto_portal_link_user(user)
            _logger.info(
                "hr_employee_auto_portal: created portal user id=%s login=%r for employee id=%s (%s)",
                user.id,
                login,
                employee.id,
                employee.name,
            )

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees.with_context(hr_employee_auto_portal=True)._hr_auto_portal_create_user()
        return employees

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("hr_employee_auto_portal"):
            _logger.debug(
                "hr_employee_auto_portal: write skip follow-up (hr_employee_auto_portal context) ids=%s",
                self.ids,
            )
            return res
        # Form saves often include user_id=False when empty; only skip auto-portal if HR set a real user.
        if vals.get("user_id"):
            _logger.info(
                "hr_employee_auto_portal: write skip auto-portal — manual user_id=%s set on ids=%s",
                vals.get("user_id"),
                self.ids,
            )
            return res
        # Try on any save so "Save" still creates/links when email was filled earlier.
        to_process = self.filtered(lambda e: not e.user_id).sudo()
        if to_process:
            _logger.info(
                "hr_employee_auto_portal: write will try auto-portal for %s employee(s) ids=%s",
                len(to_process),
                to_process.ids,
            )
            to_process._hr_auto_portal_create_user()
        else:
            _logger.info(
                "hr_employee_auto_portal: write skip auto-portal — all %s employee(s) already have user_id",
                len(self),
            )
        return res
