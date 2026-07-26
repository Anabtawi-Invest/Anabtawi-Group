# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AiScoringDimension(models.Model):
    _name = 'ai.scoring.dimension'
    _description = 'AI Scoring Dimension'
    _order = 'sequence, id'

    name = fields.Char(
        string='Dimension Name',
        required=True,
        help='Name of the scoring dimension (e.g., Leadership, Creativity, Domain Knowledge).',
    )
    code = fields.Char(
        string='Code',
        required=True,
        help='Unique short code for this dimension (e.g., leadership, creativity). Used internally.',
    )
    description = fields.Text(
        string='Description',
        help=(
            'Describe what this dimension evaluates. This text is sent to the AI '
            'to guide its scoring. Be specific.\n\n'
            'Example: "Evaluate the candidate\'s ability to lead teams, delegate tasks, '
            'manage conflicts, and drive results through others."'
        ),
    )
    icon = fields.Char(
        string='Icon (Emoji)',
        default='📋',
        help='Emoji icon displayed in the UI next to this dimension.',
    )
    weight = fields.Integer(
        string='Default Weight (%)',
        default=20,
        help='Default weight percentage for this dimension in the overall score.',
    )
    is_default = fields.Boolean(
        string='Include by Default',
        default=False,
        help='If checked, this dimension is automatically included for new job positions.',
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )
    color = fields.Char(
        string='Color',
        default='#714B67',
        help='Color code for progress bars and charts (hex format).',
    )

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Dimension code must be unique!'),
    ]

    @api.constrains('weight')
    def _check_weight(self):
        for rec in self:
            if rec.weight < 0 or rec.weight > 100:
                raise ValidationError(_(
                    'Weight for "%s" must be between 0 and 100.', rec.name
                ))


class AiScoringDimensionLine(models.Model):
    """Links a scoring dimension to a specific job position with a custom weight."""
    _name = 'ai.scoring.dimension.line'
    _description = 'Job Position Scoring Dimension'
    _order = 'sequence, id'

    job_id = fields.Many2one(
        'hr.job',
        string='Job Position',
        required=True,
        ondelete='cascade',
    )
    dimension_id = fields.Many2one(
        'ai.scoring.dimension',
        string='Dimension',
        required=True,
        ondelete='restrict',
    )
    weight = fields.Integer(
        string='Weight (%)',
        default=20,
        help='Weight of this dimension for this specific job position.',
    )
    sequence = fields.Integer(
        string='Sequence',
        related='dimension_id.sequence',
        store=True,
    )
    dimension_code = fields.Char(
        related='dimension_id.code',
        store=True,
    )
    dimension_description = fields.Text(
        related='dimension_id.description',
    )
    dimension_icon = fields.Char(
        related='dimension_id.icon',
    )

    @api.constrains('weight')
    def _check_weight(self):
        for rec in self:
            if rec.weight < 0 or rec.weight > 100:
                raise ValidationError(_(
                    'Weight must be between 0 and 100.'
                ))


class AiApplicantScore(models.Model):
    """Stores individual dimension scores for each applicant."""
    _name = 'ai.applicant.score'
    _description = 'Applicant AI Dimension Score'
    _order = 'sequence, id'

    applicant_id = fields.Many2one(
        'hr.applicant',
        string='Applicant',
        required=True,
        ondelete='cascade',
    )
    dimension_id = fields.Many2one(
        'ai.scoring.dimension',
        string='Dimension',
        required=True,
        ondelete='restrict',
    )
    score = fields.Float(
        string='Score',
        default=0,
        help='AI-generated score for this dimension (0–100).',
    )
    weight = fields.Integer(
        string='Weight (%)',
        default=20,
    )
    weighted_score = fields.Float(
        string='Weighted Score',
        compute='_compute_weighted_score',
        store=True,
    )
    sequence = fields.Integer(
        string='Sequence',
        related='dimension_id.sequence',
        store=True,
    )
    dimension_code = fields.Char(
        related='dimension_id.code',
        store=True,
    )
    dimension_icon = fields.Char(
        related='dimension_id.icon',
    )
    dimension_color = fields.Char(
        related='dimension_id.color',
    )

    @api.depends('score', 'weight')
    def _compute_weighted_score(self):
        for rec in self:
            rec.weighted_score = (rec.score * rec.weight) / 100.0 if rec.weight else 0
