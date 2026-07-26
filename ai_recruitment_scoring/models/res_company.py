# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResCompany(models.Model):
    _inherit = 'res.company'

    # ---------------------
    # AI Provider Settings
    # ---------------------
    ai_provider = fields.Selection(
        selection=[
            ('gemini', 'Google Gemini'),
            ('openai', 'OpenAI'),
        ],
        string='AI Provider',
        default='gemini',
        help='Select the AI provider for recruitment scoring.',
    )
    ai_api_key = fields.Char(
        string='API Key',
        help='API key for the selected AI provider. Stored securely.',
        groups='ai_recruitment_scoring.group_ai_recruitment_manager',
    )
    ai_model = fields.Char(
        string='AI Model',
        default='gemini-2.0-flash',
        help=(
            'Model identifier. Examples:\n'
            '  Gemini: gemini-2.0-flash, gemini-2.5-pro\n'
            '  OpenAI: gpt-4o, gpt-4o-mini'
        ),
    )
    ai_language = fields.Selection(
        selection=[
            ('en', 'English'),
            ('ar', 'Arabic'),
            ('fr', 'French'),
            ('es', 'Spanish'),
            ('de', 'German'),
            ('pt', 'Portuguese'),
            ('zh', 'Chinese'),
            ('ja', 'Japanese'),
            ('ko', 'Korean'),
            ('tr', 'Turkish'),
            ('id', 'Indonesian'),
            ('hi', 'Hindi'),
        ],
        string='AI Response Language',
        default='en',
        help='Language for AI-generated summaries and interview questions.',
    )
    ai_max_questions = fields.Integer(
        string='Max Interview Questions',
        default=10,
        help='Maximum number of interview questions to generate per applicant.',
    )
    ai_temperature = fields.Float(
        string='AI Temperature',
        default=0.3,
        help=(
            'Controls creativity vs. consistency of AI responses. '
            '0.0 = very deterministic, 1.0 = very creative. '
            'Recommended: 0.2–0.4 for scoring, 0.5–0.7 for questions.'
        ),
    )

    # ---------------------
    # Notification Settings
    # ---------------------
    ai_notify_odoo = fields.Boolean(
        string='Odoo Notification',
        default=True,
        help='Send an Odoo internal notification (chat/inbox) when AI analysis completes.',
    )
    ai_notify_email = fields.Boolean(
        string='Email Notification (Optional)',
        default=False,
        help='Also send an email notification when AI analysis completes. Useful for bulk operations.',
    )
    ai_notify_user_ids = fields.Many2many(
        'res.users',
        'company_ai_notify_user_rel',
        'company_id',
        'user_id',
        string='Notify Users',
        help='Additional users to notify when AI analysis completes (besides the user who triggered it).',
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ai_provider = fields.Selection(
        related='company_id.ai_provider',
        readonly=False,
    )
    ai_api_key = fields.Char(
        related='company_id.ai_api_key',
        readonly=False,
    )
    ai_model = fields.Char(
        related='company_id.ai_model',
        readonly=False,
    )
    ai_language = fields.Selection(
        related='company_id.ai_language',
        readonly=False,
    )
    ai_max_questions = fields.Integer(
        related='company_id.ai_max_questions',
        readonly=False,
    )
    ai_temperature = fields.Float(
        related='company_id.ai_temperature',
        readonly=False,
    )
    ai_notify_odoo = fields.Boolean(
        related='company_id.ai_notify_odoo',
        readonly=False,
    )
    ai_notify_email = fields.Boolean(
        related='company_id.ai_notify_email',
        readonly=False,
    )
    ai_notify_user_ids = fields.Many2many(
        related='company_id.ai_notify_user_ids',
        readonly=False,
    )
