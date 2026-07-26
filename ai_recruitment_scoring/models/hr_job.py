# -*- coding: utf-8 -*-
from odoo import models, fields, api


class HrJob(models.Model):
    _inherit = 'hr.job'

    # ----------------------------
    # AI Scoring Criteria Fields
    # ----------------------------
    ai_required_skills = fields.Text(
        string='Required Skills (AI)',
        help=(
            'Comma-separated list of required skills for AI matching.\n'
            'Example: Python, Odoo, PostgreSQL, REST API, Git'
        ),
    )
    ai_preferred_skills = fields.Text(
        string='Preferred Skills (AI)',
        help=(
            'Comma-separated list of nice-to-have skills.\n'
            'Example: Docker, CI/CD, TypeScript, Machine Learning'
        ),
    )
    ai_experience_years = fields.Integer(
        string='Min. Experience (Years)',
        default=0,
        help='Minimum years of relevant experience for optimal scoring.',
    )
    ai_education_level = fields.Selection(
        selection=[
            ('none', 'No Requirement'),
            ('high_school', 'High School'),
            ('associate', 'Associate Degree'),
            ('bachelor', 'Bachelor\'s Degree'),
            ('master', 'Master\'s Degree'),
            ('phd', 'PhD / Doctorate'),
        ],
        string='Min. Education Level',
        default='none',
        help='Minimum education level for AI scoring.',
    )
    ai_scoring_criteria = fields.Text(
        string='Custom Scoring Criteria',
        help=(
            'Additional criteria or context for the AI to consider when scoring.\n'
            'Example: "Candidate must have experience in ERP implementation '
            'for manufacturing companies. Leadership skills are a plus."'
        ),
    )
    ai_question_focus = fields.Text(
        string='Interview Question Focus',
        help=(
            'Specific areas the AI should focus on when generating interview questions.\n'
            'Example: "Focus on problem-solving under pressure, team management, '
            'and experience with Agile methodology."'
        ),
    )

    # ----------------------------
    # Dynamic Scoring Dimensions
    # ----------------------------
    ai_dimension_line_ids = fields.One2many(
        'ai.scoring.dimension.line',
        'job_id',
        string='Scoring Dimensions',
        help='Configure which dimensions to score and their weights for this job position.',
    )
    ai_total_weight = fields.Integer(
        string='Total Weight',
        compute='_compute_ai_total_weight',
        store=False,
        help='Sum of all dimension weights. Should ideally equal 100%.',
    )

    @api.depends('ai_dimension_line_ids.weight')
    def _compute_ai_total_weight(self):
        for rec in self:
            rec.ai_total_weight = sum(rec.ai_dimension_line_ids.mapped('weight'))

    def action_load_default_dimensions(self):
        """Load all default dimensions into this job position."""
        self.ensure_one()
        default_dims = self.env['ai.scoring.dimension'].search([
            ('is_default', '=', True),
            ('active', '=', True),
        ])
        existing_dim_ids = self.ai_dimension_line_ids.mapped('dimension_id').ids
        vals_list = []
        for dim in default_dims:
            if dim.id not in existing_dim_ids:
                vals_list.append({
                    'job_id': self.id,
                    'dimension_id': dim.id,
                    'weight': dim.weight,
                })
        if vals_list:
            self.env['ai.scoring.dimension.line'].create(vals_list)
        return True
