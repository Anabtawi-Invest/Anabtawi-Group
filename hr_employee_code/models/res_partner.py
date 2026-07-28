import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    employee_number = fields.Char(
        string="Employee Number",
        compute="_compute_employee_number",
        store=True,
        index=True,
        readonly=True,
    )

    def _employee_number_domain(self, partner, company=None):
        domain = [
            "|",
            ("work_contact_id", "=", partner.id),
            ("user_partner_id", "=", partner.id),
        ]
        if company:
            return [("company_id", "=", company.id), *domain]
        if self.env.company:
            return [("company_id", "=", self.env.company.id), *domain]
        return domain

    def _get_employee_for_partner(self, partner, company=None):
        return self.env["hr.employee"].sudo().search(
            self._employee_number_domain(partner, company=company),
            limit=1,
        )

    @api.depends("employee_ids.employee_number", "employee_ids.company_id")
    def _compute_employee_number(self):
        for partner in self:
            employee = partner._get_employee_for_partner(partner)
            partner.employee_number = employee.employee_number if employee else False

    @api.model
    def _extract_pos_search_term(self, domain):
        for item in domain or []:
            if isinstance(item, (list, tuple)) and len(item) == 3 and item[1] == "ilike":
                return item[2]
        return None

    @api.model
    def _search_partners_by_employee_number(self, term, company):
        if not term or not company:
            _logger.info(
                "[hr_employee_code] _search_partners_by_employee_number skipped term=%r company=%s",
                term,
                company,
            )
            return self.browse()

        stripped = term.strip()
        employee_domain = [("company_id", "=", company.id)]
        if stripped.isdigit():
            employee_domain += [
                "|",
                ("employee_number", "=", stripped),
                ("employee_number", "ilike", stripped),
            ]
        else:
            employee_domain.append(("employee_number", "ilike", term))

        employees = self.env["hr.employee"].sudo().search(employee_domain, limit=100)
        _logger.info(
            "[hr_employee_code] _search_partners_by_employee_number term=%r company=%s (%s) "
            "domain=%s employees_found=%s details=%s",
            term,
            company.id,
            company.display_name,
            employee_domain,
            len(employees),
            [
                {
                    "id": e.id,
                    "name": e.name,
                    "employee_number": e.employee_number,
                    "work_contact_id": e.work_contact_id.id,
                    "user_partner_id": e.user_partner_id.id,
                }
                for e in employees
            ],
        )

        partner_ids = set()
        for employee in employees:
            if employee.work_contact_id:
                partner_ids.add(employee.work_contact_id.id)
            if employee.user_partner_id:
                partner_ids.add(employee.user_partner_id.id)

        partners = self.browse(list(partner_ids))
        _logger.info(
            "[hr_employee_code] _search_partners_by_employee_number partner_ids=%s partners=%s",
            list(partner_ids),
            [(p.id, p.display_name) for p in partners],
        )
        return partners

    @api.model
    def get_new_partner(self, config_id, domain, offset):
        config = self.env["pos.config"].browse(config_id)
        company = config.company_id
        search_term = self._extract_pos_search_term(domain) if domain else None

        _logger.info(
            "[hr_employee_code] get_new_partner config=%s company=%s (%s) offset=%s "
            "search_term=%r domain=%s",
            config_id,
            company.id,
            company.display_name,
            offset,
            search_term,
            domain,
        )

        if len(domain) == 0:
            limited_partner_ids = {
                partner[0] for partner in config.get_limited_partners_loading(offset)
            }
            domain += [("id", "in", list(limited_partner_ids))]
            new_partners = self.search(domain)
            employee_partners = self.browse()
        else:
            employee_partners = self.browse()
            if search_term:
                employee_partners = self._search_partners_by_employee_number(
                    search_term, company
                )
            if employee_partners:
                new_partners = employee_partners
                if offset == 0:
                    domain_matches = self.search(domain, limit=100)
                    new_partners = employee_partners | domain_matches
            else:
                new_partners = self.search(domain, offset=offset, limit=100)

        _logger.info(
            "[hr_employee_code] get_new_partner domain_results=%s employee_results=%s merged=%s",
            [(p.id, p.display_name, p.employee_number) for p in new_partners - employee_partners],
            [(p.id, p.display_name, p.employee_number) for p in employee_partners],
            [(p.id, p.display_name, p.employee_number) for p in new_partners],
        )

        fiscal_positions = new_partners.fiscal_position_id
        partner_data = self._load_pos_data_read(new_partners, config)
        _logger.info(
            "[hr_employee_code] get_new_partner loaded_data=%s",
            [
                {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "employee_number": row.get("employee_number"),
                }
                for row in partner_data
            ],
        )
        return {
            "res.partner": partner_data,
            "account.fiscal.position": self.env["account.fiscal.position"]._load_pos_data_read(
                fiscal_positions, config
            ),
        }

    @api.model
    def _load_pos_data_read(self, records, config):
        result = super()._load_pos_data_read(records, config)
        if not result or not config:
            return result

        company = config.company_id
        by_id = {row["id"]: row for row in result}
        for partner in records:
            employee = partner._get_employee_for_partner(partner, company=company)
            if partner.id in by_id:
                by_id[partner.id]["employee_number"] = employee.employee_number or False

        return result

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        if "employee_number" not in fields_list:
            fields_list.append("employee_number")
        return fields_list
