from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrKpiCategory(models.Model):
    _name = "anabtawi.hr.kpi.category"
    _description = "HR KPI Category"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    description = fields.Text(translate=True)

    _sql_constraints = [
        ("code_unique", "unique(code)", "KPI category code must be unique."),
    ]


class HrKpiDefinition(models.Model):
    _name = "anabtawi.hr.kpi.definition"
    _description = "HR KPI Definition"
    _order = "category_id, sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True)
    category_id = fields.Many2one("anabtawi.hr.kpi.category", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    unit = fields.Selection([
        ("number", "Number"),
        ("percent", "Percent"),
        ("currency", "Currency"),
        ("days", "Days"),
        ("hours", "Hours"),
        ("ratio", "Ratio"),
    ], default="number", required=True)
    direction = fields.Selection([
        ("higher", "Higher is better"),
        ("lower", "Lower is better"),
        ("neutral", "Neutral"),
    ], default="neutral", required=True)
    active = fields.Boolean(default=True)
    formula = fields.Text(translate=True)
    source_note = fields.Text(translate=True)
    iso_area = fields.Char(string="ISO 30414 Area", translate=True)
    auto_compute = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_unique", "unique(code)", "KPI definition code must be unique."),
    ]


class HrKpiPeriod(models.Model):
    _name = "anabtawi.hr.kpi.period"
    _description = "HR KPI Reporting Period"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_from desc, date_to desc"

    name = fields.Char(required=True, tracking=True)
    date_from = fields.Date(required=True, tracking=True)
    date_to = fields.Date(required=True, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
    state = fields.Selection([
        ("draft", "Draft"),
        ("computed", "Computed"),
        ("approved", "Approved"),
    ], default="draft", tracking=True)
    snapshot_ids = fields.One2many("anabtawi.hr.kpi.snapshot", "period_id")
    snapshot_count = fields.Integer(compute="_compute_snapshot_count")

    @api.depends("snapshot_ids")
    def _compute_snapshot_count(self):
        for rec in self:
            rec.snapshot_count = len(rec.snapshot_ids)

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise UserError(_("Date From must be before Date To."))

    def action_compute(self):
        for rec in self:
            rec._compute_kpis()
            rec.state = "computed"
        return True

    def action_approve(self):
        self.write({"state": "approved"})

    def action_reset_draft(self):
        self.write({"state": "draft"})

    def _employees_domain(self):
        self.ensure_one()
        return [("company_id", "in", [False, self.company_id.id])]

    def _active_employees(self):
        self.ensure_one()
        domain = self._employees_domain() + [("active", "=", True)]
        return self.env["hr.employee"].search(domain)

    def _period_contracts(self):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("date_start", "<=", self.date_to),
            "|", ("date_end", "=", False), ("date_end", ">=", self.date_from),
        ]
        return self.env["hr.contract"].search(domain)

    def _sum_payslip_or_contract_costs(self):
        """Best effort: use contracts when payroll is not installed."""
        contracts = self._period_contracts()
        months = max(1, (self.date_to.year - self.date_from.year) * 12 + self.date_to.month - self.date_from.month + 1)
        return sum((c.wage or 0.0) * months for c in contracts)

    def _get_revenue(self):
        self.ensure_one()
        Move = self.env["account.move"]
        domain = [
            ("company_id", "=", self.company_id.id),
            ("move_type", "in", ["out_invoice", "out_refund"]),
            ("state", "=", "posted"),
            ("invoice_date", ">=", self.date_from),
            ("invoice_date", "<=", self.date_to),
        ]
        total = 0.0
        for move in Move.search(domain):
            sign = -1 if move.move_type == "out_refund" else 1
            total += sign * (move.amount_untaxed_signed or 0.0)
        return total

    def _count_departures(self, voluntary=False):
        self.ensure_one()
        Employee = self.env["hr.employee"].with_context(active_test=False)
        domain = self._employees_domain() + [
            ("active", "=", False),
            ("write_date", ">=", fields.Datetime.to_string(fields.Datetime.to_datetime(self.date_from))),
            ("write_date", "<=", fields.Datetime.to_string(fields.Datetime.to_datetime(self.date_to) + relativedelta(days=1))),
        ]
        # Odoo standard does not always store termination reason; manual correction can be entered on snapshot.
        return Employee.search_count(domain)

    def _leave_days(self, only_unplanned=True):
        self.ensure_one()
        Leave = self.env["hr.leave"]
        domain = [
            ("company_id", "in", [False, self.company_id.id]),
            ("state", "=", "validate"),
            ("request_date_from", "<=", self.date_to),
            ("request_date_to", ">=", self.date_from),
        ]
        if only_unplanned and "holiday_status_id" in Leave._fields:
            # Sick/unpaid/absence are counted as absenteeism. Annual vacation is intentionally excluded where named clearly.
            domain += ["|", ("holiday_status_id.name", "ilike", "sick"), ("holiday_status_id.name", "ilike", "absence")]
        return sum(Leave.search(domain).mapped("number_of_days") or [0.0])

    def _work_days_available(self, employee_count):
        self.ensure_one()
        days = (self.date_to - self.date_from).days + 1
        return max(0, employee_count * days)

    def _compute_kpis(self):
        self.ensure_one()
        definitions = self.env["anabtawi.hr.kpi.definition"].search([("active", "=", True)])
        employees = self._active_employees()
        employee_count = len(employees)
        contracts = self._period_contracts()
        revenue = self._get_revenue()
        workforce_cost = self._sum_payslip_or_contract_costs()
        departures = self._count_departures()
        leave_days = self._leave_days()
        available_days = self._work_days_available(employee_count)

        Applicant = self.env["hr.applicant"]
        applicants = Applicant.search_count([
            ("company_id", "in", [False, self.company_id.id]),
            ("create_date", ">=", fields.Datetime.to_string(fields.Datetime.to_datetime(self.date_from))),
            ("create_date", "<=", fields.Datetime.to_string(fields.Datetime.to_datetime(self.date_to) + relativedelta(days=1))),
        ])

        metrics = {
            "WORKFORCE_HEADCOUNT": employee_count,
            "ACTIVE_CONTRACTS": len(contracts),
            "FTE": employee_count,  # Can be manually adjusted if part-time schedules are configured differently.
            "TOTAL_WORKFORCE_COST": workforce_cost,
            "TOTAL_EMPLOYMENT_COST": workforce_cost,
            "REVENUE_PER_EMPLOYEE": revenue / employee_count if employee_count else 0.0,
            "HUMAN_CAPITAL_ROI": ((revenue - workforce_cost) / workforce_cost) if workforce_cost else 0.0,
            "TURNOVER_RATE": (departures / employee_count * 100.0) if employee_count else 0.0,
            "DEPARTURES": departures,
            "ABSENTEEISM_RATE": (leave_days / available_days * 100.0) if available_days else 0.0,
            "ABSENT_DAYS": leave_days,
            "RECRUITMENT_CANDIDATES": applicants,
            "AVG_SALARY": (sum(contracts.mapped("wage")) / len(contracts)) if contracts else 0.0,
            "SPAN_OF_CONTROL": self._span_of_control(employees),
            "INTERNAL_MOBILITY_RATE": 0.0,
            "TRAINING_PARTICIPATION_RATE": 0.0,
            "GRIEVANCES": 0.0,
            "DISCIPLINARY_ACTIONS": 0.0,
            "OCCUPATIONAL_ACCIDENTS": 0.0,
            "FATALITY_RATE": 0.0,
        }

        Snapshot = self.env["anabtawi.hr.kpi.snapshot"]
        for definition in definitions:
            value = metrics.get(definition.code, 0.0)
            snapshot = Snapshot.search([
                ("period_id", "=", self.id),
                ("definition_id", "=", definition.id),
                ("company_id", "=", self.company_id.id),
            ], limit=1)
            vals = {
                "period_id": self.id,
                "definition_id": definition.id,
                "category_id": definition.category_id.id,
                "company_id": self.company_id.id,
                "date_from": self.date_from,
                "date_to": self.date_to,
                "value": value,
                "unit": definition.unit,
                "direction": definition.direction,
                "auto_computed": definition.auto_compute,
            }
            if snapshot:
                snapshot.write(vals)
            else:
                Snapshot.create(vals)

    def _span_of_control(self, employees):
        managers = employees.filtered(lambda e: e.child_ids)
        if not managers:
            return 0.0
        total_direct_reports = sum(len(m.child_ids) for m in managers)
        return total_direct_reports / len(managers)


class HrKpiSnapshot(models.Model):
    _name = "anabtawi.hr.kpi.snapshot"
    _description = "HR KPI Snapshot"
    _order = "date_from desc, category_id, definition_id"

    period_id = fields.Many2one("anabtawi.hr.kpi.period", required=True, ondelete="cascade")
    definition_id = fields.Many2one("anabtawi.hr.kpi.definition", required=True, ondelete="cascade")
    category_id = fields.Many2one("anabtawi.hr.kpi.category", required=True)
    company_id = fields.Many2one("res.company", required=True)
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    value = fields.Float(digits=(16, 2))
    target_value = fields.Float(digits=(16, 2))
    unit = fields.Selection(related="definition_id.unit", store=True, readonly=False)
    direction = fields.Selection(related="definition_id.direction", store=True, readonly=False)
    auto_computed = fields.Boolean(default=True)
    manual_note = fields.Text()
    score = fields.Selection([
        ("green", "On Track"),
        ("yellow", "Watch"),
        ("red", "Needs Action"),
        ("manual", "Manual Review"),
    ], compute="_compute_score", store=True)
    display_value = fields.Char(compute="_compute_display_value")

    _sql_constraints = [
        ("period_definition_company_unique", "unique(period_id, definition_id, company_id)", "One KPI snapshot per period/company is allowed."),
    ]

    @api.depends("value", "target_value", "direction")
    def _compute_score(self):
        for rec in self:
            if not rec.target_value:
                rec.score = "manual"
            elif rec.direction == "higher":
                rec.score = "green" if rec.value >= rec.target_value else "red"
            elif rec.direction == "lower":
                rec.score = "green" if rec.value <= rec.target_value else "red"
            else:
                rec.score = "manual"

    @api.depends("value", "unit")
    def _compute_display_value(self):
        for rec in self:
            if rec.unit == "percent":
                rec.display_value = f"{rec.value:.2f}%"
            elif rec.unit == "currency":
                rec.display_value = f"{rec.value:,.2f}"
            elif rec.unit == "ratio":
                rec.display_value = f"{rec.value:.2f}"
            elif rec.unit == "days":
                rec.display_value = f"{rec.value:.2f} days"
            elif rec.unit == "hours":
                rec.display_value = f"{rec.value:.2f} hours"
            else:
                rec.display_value = f"{rec.value:,.2f}"
