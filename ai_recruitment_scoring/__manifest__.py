# -*- coding: utf-8 -*-
{
    'name': 'AI Recruitment Scoring',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Recruitment',
    'summary': 'AI-Powered CV Analysis, Smart Scoring & Interview Question Generation',
    'description': """
AI Recruitment Scoring Module for Odoo 19
==========================================

Enhance your recruitment workflow with AI-powered intelligence:

* **Multi-Dimensional CV Scoring** — Skills, Experience, Education & Cultural Fit
* **AI-Generated Summaries** — Instant candidate insights from uploaded CVs
* **Smart Interview Questions** — Context-aware, categorized questions with difficulty levels
* **Bulk Scoring** — Process multiple applicants simultaneously
* **Skill Gap Analysis** — Visual gap reports vs job requirements
* **Multi-Provider Support** — Google Gemini & OpenAI integration

Supports PDF and DOCX resume formats with automatic text extraction.
    """,
    'author': 'Anabtawi Group',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'hr_recruitment',
        'hr',
        'mail',
        'calendar',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'wizards/bulk_score_wizard_views.xml',
        'views/res_company_views.xml',
        'views/hr_job_views.xml',
        'views/hr_applicant_views.xml',
        'views/menu.xml',
    ],
    'assets': {},
    'installable': True,
    'application': False,
    'auto_install': False,
    'images': ['static/description/icon.png'],
}
