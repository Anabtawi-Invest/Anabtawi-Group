# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # ------------------------------
    # Missing single fields (PDF)
    # ------------------------------
    sb_employee_number = fields.Char(string="Employee Number")
    sb_start_date = fields.Date(string="Start Date")
    sb_alternate_name = fields.Char(string="Alternate Name")
    sb_birth_place = fields.Char(string="Place of Birth")
    sb_mother_name = fields.Char(string="Mother Name")
    sb_ss_number = fields.Char(string="Social Security Number")
    sb_income_tax_number = fields.Char(string="Income Tax Number")
    sb_bank_branch = fields.Char(string="Bank Branch")
    sb_blood_type = fields.Selection(
        [
            ("a_plus", "A+"), ("a_minus", "A-"),
            ("b_plus", "B+"), ("b_minus", "B-"),
            ("ab_plus", "AB+"), ("ab_minus", "AB-"),
            ("o_plus", "O+"), ("o_minus", "O-"),
        ],
        string="Blood Type",
    )

    # ------------------------------
    # Salary fields (no hr_contract required)
    # ------------------------------
    sb_basic_salary = fields.Float(string="Basic Salary")
    sb_ss_salary = fields.Float(string="SS Salary")
    sb_service_charge = fields.Float(string="Service Charge")
    sb_points = fields.Float(string="Points")

    # ------------------------------
    # One2many tables
    # ------------------------------
    sb_dependent_ids = fields.One2many("sb.hr.dependent", "employee_id", string="Dependents")
    sb_warning_ids = fields.One2many("sb.hr.warning", "employee_id", string="Warnings")
    sb_previous_job_ids = fields.One2many("sb.hr.previous.job", "employee_id", string="Previous Jobs")
    sb_education_ids = fields.One2many("sb.hr.education", "employee_id", string="Education")
    sb_official_document_ids = fields.One2many("sb.hr.official.document", "employee_id", string="Official Documents")
    sb_career_movement_ids = fields.One2many("sb.hr.career.movement", "employee_id", string="Career Movements")

    def _sb_active_contract(self):
        """Return active contract if hr_contract exists; otherwise False."""
        self.ensure_one()
        if not self.env.registry.get("hr.contract"):
            return False
        return self.env["hr.contract"].search(
            [("employee_id", "=", self.id), ("state", "in", ("open", "draft"))],
            order="state asc, date_start desc, id desc",
            limit=1,
        )

    def sb_profile_payload(self):
        """Return a dict used by the QWeb PDF report."""
        self.ensure_one()

        contract = self._sb_active_contract()
        wage = contract.wage if contract and hasattr(contract, "wage") else 0.0

        payload = {
            "number": self.sb_employee_number or self.barcode or self.pin or "",
            "name": self.name or "",
            "alt_name": self.sb_alternate_name or "",
            "start_date": self.sb_start_date or "",
            "job": self.job_title or (self.job_id.name if self.job_id else ""),
            "type": getattr(self, "employee_type", "") or "",
            "religion": getattr(self, "religion", "") or "",

            "gender": self.gender or "",
            "marital": self.marital or "",
            "nationality": self.country_id.name if self.country_id else "",
            "national_number": self.identification_id or "",
            "ss_number": self.sb_ss_number or "",
            "mother_name": self.sb_mother_name or "",
            "medical_insurance": getattr(self, "medical_insurance", "") or "",

            "bank": (self.bank_account_id.bank_id.name if self.bank_account_id and self.bank_account_id.bank_id else ""),
            "bank_branch": self.sb_bank_branch or "",
            "income_tax_number": self.sb_income_tax_number or "",

            "birth_date": self.birthday or "",
            "birth_place": self.sb_birth_place or "",
            "home_phone": self.private_phone or "",
            "mobile": self.mobile_phone or "",
            "status": "Current" if self.active else "Inactive",
            "termination_date": getattr(self, "departure_date", "") or "",

            "city": getattr(self, "private_city", "") or getattr(self, "city", "") or "",
            "address": " ".join([p for p in [getattr(self, "private_street", ""), getattr(self, "private_street2", "")] if p]).strip(),
            "email": self.work_email or getattr(self, "private_email", "") or "",
            "blood_type": self.sb_blood_type or "",

            "basic_salary": wage or self.sb_basic_salary or 0.0,
            "ss_salary": self.sb_ss_salary or (wage or self.sb_basic_salary or 0.0),
            "service_charge": self.sb_service_charge or 0.0,
            "points": self.sb_points or 0.0,

            "dependants": [],
            "warnings": [],
            "previous_jobs": [],
            "education": [],
            "official_docs": [],
            "career_moves": [],
        }

        for d in self.sb_dependent_ids:
            payload["dependants"].append({
                "name": d.name or "",
                "birth_date": d.birth_date or "",
                "birth_place": d.birth_place or "",
                "medical_ins": d.medical_insurance or "",
                "cover": bool(d.cover),
            })

        for w in self.sb_warning_ids:
            payload["warnings"].append({
                "date": w.date or "",
                "type": w.warning_type or "",
                "reason": w.reason or "",
            })

        for j in self.sb_previous_job_ids:
            payload["previous_jobs"].append({
                "employer": j.employer or "",
                "start_date": j.start_date or "",
                "end_date": j.end_date or "",
                "occupation": j.occupation or "",
                "termination_reason": j.termination_reason or "",
            })

        for e in self.sb_education_ids:
            payload["education"].append({
                "year": e.year or "",
                "degree": e.degree or "",
                "specialty": e.specialty or "",
                "institute": e.institute or "",
            })

        for doc in self.sb_official_document_ids:
            payload["official_docs"].append({
                "type": doc.doc_type or "",
                "number": doc.number or "",
                "issue_place": doc.issue_place or "",
                "issue_date": doc.issue_date or "",
                "expiry_date": doc.expiry_date or "",
            })

        for m in self.sb_career_movement_ids:
            payload["career_moves"].append({
                "type": m.movement_type or "",
                "date": m.date or "",
                "old": m.old or "",
                "new": m.new or "",
            })

        return payload
