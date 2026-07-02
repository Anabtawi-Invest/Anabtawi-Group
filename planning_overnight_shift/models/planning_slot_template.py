# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import timedelta

class PlanningSlotTemplate(models.Model):
    _inherit = 'planning.slot.template'

    start_time_12 = fields.Float('Start Hour (12h)', default=8.0)
    start_am_pm = fields.Selection([('AM', 'AM'), ('PM', 'PM')], string='Start AM/PM', default='AM')
    end_time_12 = fields.Float('End Hour (12h)', default=5.0)
    end_am_pm = fields.Selection([('AM', 'AM'), ('PM', 'PM')], string='End AM/PM', default='PM')

    start_time = fields.Float(compute='_compute_times_24', inverse='_inverse_times_24', store=True)
    end_time = fields.Float(compute='_compute_times_24', inverse='_inverse_times_24', store=True)

    @api.depends('start_time_12', 'start_am_pm', 'end_time_12', 'end_am_pm')
    def _compute_times_24(self):
        for rec in self:
            # start_time
            start_val = rec.start_time_12 or 0.0
            if start_val > 12.0:
                start_val = 12.0
            elif start_val < 0.0:
                start_val = 0.0
            
            if rec.start_am_pm == 'PM':
                rec.start_time = (start_val % 12.0) + 12.0 if (start_val % 12.0) != 0.0 else 12.0
            else:
                rec.start_time = start_val % 12.0
                
            # end_time
            end_val = rec.end_time_12 or 0.0
            if end_val > 12.0:
                end_val = 12.0
            elif end_val < 0.0:
                end_val = 0.0
                
            if rec.end_am_pm == 'PM':
                rec.end_time = (end_val % 12.0) + 12.0 if (end_val % 12.0) != 0.0 else 12.0
            else:
                rec.end_time = end_val % 12.0

    def _inverse_times_24(self):
        for rec in self:
            # start
            h_start = rec.start_time
            if h_start >= 12.0:
                rec.start_am_pm = 'PM'
                rec.start_time_12 = 12.0 if h_start == 12.0 else h_start - 12.0
            else:
                rec.start_am_pm = 'AM'
                rec.start_time_12 = 12.0 if h_start == 0.0 else h_start

            # end
            h_end = rec.end_time
            if h_end >= 12.0:
                rec.end_am_pm = 'PM'
                rec.end_time_12 = 12.0 if h_end == 12.0 else h_end - 12.0
            else:
                rec.end_am_pm = 'AM'
                rec.end_time_12 = 12.0 if h_end == 0.0 else h_end

    def _check_start_and_end_times(self):
        # Override the base constraint check to bypass/disable the ValidationError
        # for overnight shift templates where start_time > end_time.
        pass

class PlanningSlot(models.Model):
    _inherit = 'planning.slot'

    @api.model
    def _calculate_start_end_dates(self, start_datetime, end_datetime, resource_id, template_id, previous_template_id, template_reset):
        start, end = super()._calculate_start_end_dates(
            start_datetime, end_datetime, resource_id, template_id, previous_template_id, template_reset
        )
        # If a template is applied and it is an overnight shift template (start_time > end_time),
        # we adjust the end_datetime by adding 1 day because the shift ends on the next calendar day.
        if template_id and start_datetime and template_id.end_time < template_id.start_time:
            end = end + timedelta(days=1)
        return (start, end)

    def _different_than_template(self, check_empty=True):
        self.ensure_one()
        if not self.template_id:
            return True
        if not self.start_datetime or not self.end_datetime:
            return True
            
        if self.template_id.end_time < self.template_id.start_time:
            # It's an overnight template.
            # We copy Odoo's logic but adjust duration_days check by adding 1 day to expected days span
            import pytz
            from math import modf
            from odoo.addons.planning.models.planning_slot import days_span
            
            template_fields = self._get_template_fields().items()
            for template_field, slot_field in template_fields:
                if self.template_id[template_field] or not check_empty:
                    if template_field in ('start_time', 'end_time'):
                        h = int(self.template_id[template_field])
                        m = round(modf(self.template_id[template_field])[0] * 60.0)
                        slot_time = self[slot_field].astimezone(pytz.timezone(self._get_tz()))
                        if slot_time.hour != h or slot_time.minute != m:
                            return True
                    elif template_field == 'duration_days':
                        expected_days = self.template_id.duration_days + 1
                        if days_span(self.start_datetime, self.end_datetime) != expected_days:
                            return True
                    elif self[slot_field] != self.template_id[template_field]:
                        return True
            return False
            
        return super()._different_than_template(check_empty=check_empty)
