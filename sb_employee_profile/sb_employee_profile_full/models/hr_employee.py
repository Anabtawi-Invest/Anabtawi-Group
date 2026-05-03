# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # --- Safe helpers -------------------------------------------------
    def _sb_has_field(self, field_name: str) -> bool:
        return field_name in self._fields

    def _sb_get(self, field_name: str, default=""):
        """Safe getter for standard/custom fields."""
        if self._sb_has_field(field_name):
            val = self[field_name]
            return val if val not in (False, None) else default
        return default

    def _sb_active_contract(self):
        """
        Return active contract if hr_contract is installed, else False.
        IMPORTANT: do NOT import or depend on hr_contract.
        """
        self.ensure_one()
        if not self.env.registry.get("hr.contract"):
            return False

        contract = self.env["hr.contract"].search(
            [("employee_id", "=", self.id), ("state", "in", ("open", "draft"))],
            order="state asc, date_start desc, id desc",
            limit=1,
        )
        return contract

    # --- Payload for QWeb report --------------------------------------
    def sb_profile_payload(self):
        """Return a dict used by the QWeb PDF report."""
        self.ensure_one()

        # Salary: use contract wage if available, otherwise employee field
        contract = self._sb_active_contract()
        wage = ""
        if contract and hasattr(contract, "wage"):
            wage = contract.wage

        payload = {
            "number": self._sb_get("sb_employee_number") or self._sb_get("barcode") or self._sb_get("pin"),
            "name": self.name or "",
            "alt_name": self._sb_get("sb_alternate_name"),
            "start_date": self._sb_get("sb_start_date"),
            "job": self._sb_get("job_title") or (self.job_id.name if self.job_id else ""),
            "type": self._sb_get("employee_type"),
            "religion": self._sb_get("religion"),

            "gender": self._sb_get("gender"),
            "marital": self._sb_get("marital"),
            "nationality": self.country_id.name if self.country_id else "",
            "national_number": self._sb_get("identification_id"),
            "ss_number": self._sb_get("sb_ss_number"),
            "mother_name": self._sb_get("sb_mother_name"),
            "medical_insurance": self._sb_get("medical_insurance"),

            "bank": (self.bank_account_id.bank_id.name if self.bank_account_id and self.bank_account_id.bank_id else ""),
            "bank_branch": self._sb_get("sb_bank_branch"),
            "income_tax_number": self._sb_get("sb_income_tax_number"),

            "birth_date": self._sb_get("birthday"),
            "birth_place": self._sb_get("sb_birth_place"),
            "home_phone": self._sb_get("private_phone"),
            "mobile": self._sb_get("mobile_phone"),
            "status": "Current" if self.active else "Inactive",
            "termination_date": self._sb_get("departure_date"),

            "city": self._sb_get("private_city") or self._sb_get("city"),
            "address": " ".join([p for p in [self._sb_get("private_street"), self._sb_get("private_street2")] if p]).strip(),
            "email": self._sb_get("work_email") or self._sb_get("private_email"),
            "blood_type": self._sb_get("sb_blood_type"),

            # Salaries on employee (fallback if no contract)
            "basic_salary": wage or self._sb_get("sb_basic_salary") or "",
            "ss_salary": self._sb_get("sb_ss_salary") or (wage or self._sb_get("sb_basic_salary") or ""),
            "service_charge": self._sb_get("sb_service_charge") or 0.0,
            "points": self._sb_get("sb_points") or 0.0,

            # Tables (these fields must exist in your module)
            "dependants": [],
            "warnings": [],
            "previous_jobs": [],
            "education": [],
            "official_docs": [],
            "career_moves": [],
        }

        # Dependents
        if self._sb_has_field("sb_dependent_ids"):
            for d in self.sb_dependent_ids:
                payload["dependants"].append({
                    "name": d.name or "",
                    "birth_date": d.birth_date or "",
                    "birth_place": d.birth_place or "",
                    "medical_ins": d.medical_insurance or "",
                    "cover": bool(d.cover),
                })

        # Warnings
        if self._sb_has_field("sb_warning_ids"):
            for w in self.sb_warning_ids:
                payload["warnings"].append({
                    "date": w.date or "",
                    "type": w.warning_type or "",
                    "reason": w.reason or "",
                })

        # Previous Jobs
        if self._sb_has_field("sb_previous_job_ids"):
            for j in self.sb_previous_job_ids:
                payload["previous_jobs"].append({
                    "employer": j.employer or "",
                    "start_date": j.start_date or "",
                    "end_date": j.end_date or "",
                    "occupation": j.occupation or "",
                    "termination_reason": j.termination_reason or "",
                })

        # Education
        if self._sb_has_field("sb_education_ids"):
            for e in self.sb_education_ids:
                payload["education"].append({
                    "year": e.year or "",
                    "degree": e.degree or "",
                    "specialty": e.specialty or "",
                    "institute": e.institute or "",
                })

        # Official Documents
        if self._sb_has_field("sb_official_document_ids"):
            for doc in self.sb_official_document_ids:
                payload["official_docs"].append({
                    "type": doc.doc_type or "",
                    "number": doc.number or "",
                    "issue_place": doc.issue_place or "",
                    "issue_date": doc.issue_date or "",
                    "expiry_date": doc.expiry_date or "",
                })

        # Career Movements
        if self._sb_has_field("sb_career_movement_ids"):
            for m in self.sb_career_movement_ids:
                payload["career_moves"].append({
                    "type": m.movement_type or "",
                    "date": m.date or "",
                    "old": m.old or "",
                    "new": m.new or "",
                })

        return payload
