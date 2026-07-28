from odoo import api, fields, models


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
            return self.browse()
        employees = self.env["hr.employee"].sudo().search(
            [
                ("employee_number", "ilike", term),
                ("company_id", "=", company.id),
            ],
            limit=100,
        )
        partner_ids = set()
        for employee in employees:
            if employee.work_contact_id:
                partner_ids.add(employee.work_contact_id.id)
            if employee.user_partner_id:
                partner_ids.add(employee.user_partner_id.id)
        return self.browse(list(partner_ids))

    @api.model
    def get_new_partner(self, config_id, domain, offset):
        config = self.env["pos.config"].browse(config_id)
        company = config.company_id
        search_term = self._extract_pos_search_term(domain) if domain else None

        if len(domain) == 0:
            limited_partner_ids = {
                partner[0] for partner in config.get_limited_partners_loading(offset)
            }
            domain += [("id", "in", list(limited_partner_ids))]
            new_partners = self.search(domain)
        else:
            new_partners = self.search(domain, offset=offset, limit=100)
            if offset == 0 and search_term:
                employee_partners = self._search_partners_by_employee_number(
                    search_term, company
                )
                new_partners = employee_partners | new_partners

        fiscal_positions = new_partners.fiscal_position_id
        return {
            "res.partner": self._load_pos_data_read(new_partners, config),
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
