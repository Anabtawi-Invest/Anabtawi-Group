# -*- coding: utf-8 -*-
import re
from odoo import models, fields, api

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Ensure profile_contract_start_date and profile_contract_end_date exist
    profile_contract_start_date = fields.Date(string="Contract Start Date")
    profile_contract_end_date = fields.Date(string="Contract End Date")

    def get_formatted_employee_number(self):
        self.ensure_one()
        num = str(self.employee_number or '').strip()
        if num:
            stripped = num.lstrip('0')
            return stripped if stripped else '0'
        return ''

    def get_ssc_start_date(self):
        """
        Retrieve contract start date in order of priority:
        1. profile_contract_start_date
        2. contract_date_start
        3. date_start
        4. first_contract_date
        """
        self.ensure_one()
        for fname in ['profile_contract_start_date', 'contract_date_start', 'date_start', 'first_contract_date']:
            if fname in self._fields and self[fname]:
                return self[fname]
        return False

    def get_ssc_end_date(self):
        """
        Retrieve termination / contract end date in order of priority:
        1. departure_date (Termination Date)
        2. profile_termination_date
        3. termination_date
        4. profile_contract_end_date
        5. contract_date_end
        6. date_end
        """
        self.ensure_one()
        for fname in ['departure_date', 'profile_termination_date', 'termination_date', 'profile_contract_end_date', 'contract_date_end', 'date_end']:
            if fname in self._fields and self[fname]:
                return self[fname]
        return False

    def get_ssc_wage(self):
        """
        Get the Social Security monthly wage
        """
        self.ensure_one()
        for fname in ['x_studio_x_studio_ssc_wage', 'x_studio_ssc_wage', 'contract_wage', 'wage']:
            if fname in self._fields and self[fname]:
                try:
                    return float(self[fname])
                except (ValueError, TypeError):
                    pass
        return 0.0

    def get_national_id(self):
        """
        Get Jordanian National ID (national_id first, then fallback to identification_id)
        """
        self.ensure_one()
        for fname in ['national_id', 'identification_id']:
            if fname in self._fields and self[fname]:
                return str(self[fname]).strip()
        return ''

    def get_personal_id(self):
        """
        Get Personal ID (same as national_id)
        """
        self.ensure_one()
        nat_id = self.get_national_id()
        if nat_id:
            return nat_id
        if 'ssnid' in self._fields and self.ssnid:
            return str(self.ssnid).strip()
        return ''

    def get_ssc_number(self):
        """
        Get Social Security Number (ssnid)
        """
        self.ensure_one()
        if 'ssnid' in self._fields and self.ssnid:
            return str(self.ssnid).strip()
        return ''

    def is_exempt_from_ssc(self):
        """
        Check if employee is exempt from social security
        """
        self.ensure_one()
        for fname in [
            'x_studio_employee_ssc_exempt',
            'x_studio_employee_ssc_exempt_1',
            'x_studio_x_studio_exempt_from_social_security',
            'x_studio_exempt_from_social_security',
            'exempt_from_social_security'
        ]:
            if fname in self._fields and self[fname]:
                return True
        return False

    def get_arabic_name_parts(self):
        """
        Split the Arabic full name into 4 parts: (First, Father, Grandfather, Family)
        """
        self.ensure_one()
        raw_name = ""
        if 'legal_name' in self._fields and self.legal_name:
            raw_name = str(self.legal_name).strip()
        elif 'name_arabic' in self._fields and self.name_arabic:
            raw_name = str(self.name_arabic).strip()
        elif self.name:
            raw_name = str(self.name).strip()

        if not raw_name:
            return ('', '', '', '')

        tokens = raw_name.split()
        if not tokens:
            return ('', '', '', '')

        compound_prefixes = {
            'عبد', 'ابو', 'أبو', 'ابن', 'أم', 'ام', 'بنت', 'آل', 'ال', 'ذو', 'ذا', 'ذي',
            'نور', 'شمس', 'علاء', 'سيف', 'تقي', 'محي', 'بهاء', 'جمال', 'ضياء', 'عماد'
        }

        merged_tokens = []
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok in compound_prefixes and i + 1 < len(tokens):
                merged_tokens.append(f"{tok} {tokens[i+1]}")
                i += 2
            else:
                merged_tokens.append(tok)
                i += 1

        first = ''
        father = ''
        grandfather = ''
        family = ''

        if len(merged_tokens) == 1:
            first = merged_tokens[0]
        elif len(merged_tokens) == 2:
            first = merged_tokens[0]
            family = merged_tokens[1]
        elif len(merged_tokens) == 3:
            first = merged_tokens[0]
            father = merged_tokens[1]
            family = merged_tokens[2]
        elif len(merged_tokens) == 4:
            first = merged_tokens[0]
            father = merged_tokens[1]
            grandfather = merged_tokens[2]
            family = merged_tokens[3]
        else:
            first = merged_tokens[0]
            father = merged_tokens[1]
            grandfather = " ".join(merged_tokens[2:-1])
            family = merged_tokens[-1]

        return (first, father, grandfather, family)
