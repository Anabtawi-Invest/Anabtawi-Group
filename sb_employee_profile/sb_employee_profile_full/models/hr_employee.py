from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # Missing single fields for report
    sb_alternate_name = fields.Char(string="Alternate Name")
    sb_birth_place = fields.Char(string="Place of Birth")
    sb_mother_name = fields.Char(string="Mother Name")
    sb_ss_number = fields.Char(string="Social Security Number")
    sb_income_tax_number = fields.Char(string="Income Tax Number")
    sb_bank_branch = fields.Char(string="Bank Branch")
    sb_blood_type = fields.Selection([
        ("a_plus", "A+"), ("a_minus", "A-"),
        ("b_plus", "B+"), ("b_minus", "B-"),
        ("ab_plus", "AB+"), ("ab_minus", "AB-"),
        ("o_plus", "O+"), ("o_minus", "O-"),
    ], string="Blood Type")
    sb_employee_number = fields.Char(string="Employee Number")
    sb_start_date = fields.Date(string="Start Date")

    # Salary extras
    sb_basic_salary = fields.Float(string="Basic Salary")
    sb_ss_salary = fields.Float(string="SS Salary")
    sb_service_charge = fields.Float(string="Service Charge")
    sb_points = fields.Float(string="Points")

    # One2many tables
    sb_dependent_ids = fields.One2many("sb.hr.dependent", "employee_id", string="Dependents")
    sb_warning_ids = fields.One2many("sb.hr.warning", "employee_id", string="Warnings")
    sb_previous_job_ids = fields.One2many("sb.hr.previous.job", "employee_id", string="Previous Jobs")
    sb_education_ids = fields.One2many("sb.hr.education", "employee_id", string="Education")
    sb_official_document_ids = fields.One2many("sb.hr.official.document", "employee_id", string="Official Documents")
    sb_career_movement_ids = fields.One2many("sb.hr.career.movement", "employee_id", string="Career Movements")

    company_currency_id = fields.Many2one(related="company_id.currency_id", readonly=True, store=False)

   def _sb_active_contract(self):
    """Return active contract if hr_contract is installed, else False."""
    self.ensure_one()
    if not self.env.registry.get("hr.contract"):
        return False

    contract = self.env["hr.contract"].search(
        [("employee_id", "=", self.id), ("state", "in", ("open", "draft"))],
        order="state asc, date_start desc, id desc",
        limit=1,
    )
    return contract

    def sb_profile_payload(self):
        """Payload for Employee Profile PDF."""
        self.ensure_one()

        # Contracts may not be installed in all databases; keep it optional.
        contract = self._sb_active_contract()
        wage = 0.0
        start_date = self.sb_start_date or getattr(self, "first_contract_date", False) or False
        if contract:
            # If contracts exist, prefer their wage/start date
            wage = getattr(contract, "wage", 0.0) or 0.0
            start_date = getattr(contract, "date_start", False) or start_date

        # Map fields with fallback to standard fields when relevant
        payload = {
            "number": self.sb_employee_number or self.barcode or self.pin or "",
            "name": self.name or "",
            "alt_name": self.sb_alternate_name or "",
            "start_date": start_date,
            "job": self.job_title or (self.job_id.name if self.job_id else ""),
            "type": self.employee_type or "",
            "religion": "",

            "gender": self.gender or "",
            "marital": self.marital or "",
            "nationality": self.country_id.name if self.country_id else "",
            "national_number": self.identification_id or "",
            "ss_number": self.sb_ss_number or "",
            "mother_name": self.sb_mother_name or "",
            "medical_insurance": "",
            "bank": (self.bank_account_id.bank_id.name if self.bank_account_id and self.bank_account_id.bank_id else ""),
            "bank_branch": self.sb_bank_branch or "",
            "income_tax_number": self.sb_income_tax_number or "",

            "birth_date": self.birthday or False,
            "birth_place": self.sb_birth_place or "",
            "home_phone": self.private_phone or "",
            "mobile": self.mobile_phone or "",
            "status": "Current" if self.active else "Inactive",
            "termination_date": self.departure_date or False,
            "city": self.private_city or "",
            "address": " ".join([p for p in [self.private_street, self.private_street2] if p]).strip(),
            "email": self.work_email or self.private_email or "",
            "blood_type": dict(self._fields["sb_blood_type"].selection).get(self.sb_blood_type, "") if self.sb_blood_type else "",

            "basic_salary": (wage or self.sb_basic_salary or 0.0),
            "ss_salary": self.sb_ss_salary if self.sb_ss_salary else wage,
            "service_charge": self.sb_service_charge or 0.0,
            "points": self.sb_points or 0.0,

            "dependants": [{
                "name": d.name,
                "birth_date": d.birth_date,
                "birth_place": d.birth_place,
                "medical_ins": d.medical_insurance,
                "cover": d.cover,
            } for d in self.sb_dependent_ids],

            "warnings": [{
                "date": w.date,
                "type": dict(w._fields["warning_type"].selection).get(w.warning_type, ""),
                "reason": w.reason,
            } for w in self.sb_warning_ids],

            "previous_jobs": [{
                "employer": j.employer,
                "start_date": j.start_date,
                "end_date": j.end_date,
                "occupation": j.occupation,
                "termination_reason": j.termination_reason,
            } for j in self.sb_previous_job_ids],

            "education": [{
                "year": e.year,
                "degree": e.degree,
                "specialty": e.specialty,
                "institute": e.institute,
            } for e in self.sb_education_ids],

            "official_docs": [{
                "type": dict(d._fields["doc_type"].selection).get(d.doc_type, ""),
                "number": d.number,
                "issue_place": d.issue_place,
                "issue_date": d.issue_date,
                "expiry_date": d.expiry_date,
            } for d in self.sb_official_document_ids],

            "career_moves": [{
                "type": dict(m._fields["movement_type"].selection).get(m.movement_type, ""),
                "date": m.date,
                "old": m.old,
                "new": m.new,
            } for m in self.sb_career_movement_ids],
        }
        return payload
