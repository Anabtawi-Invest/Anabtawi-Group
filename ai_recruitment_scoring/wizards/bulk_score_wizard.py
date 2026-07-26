# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BulkScoreWizard(models.TransientModel):
    _name = 'ai.recruitment.bulk.score.wizard'
    _description = 'Bulk AI Scoring Wizard'

    applicant_ids = fields.Many2many(
        'hr.applicant',
        string='Applicants',
        required=True,
    )
    mode = fields.Selection(
        selection=[
            ('full', 'Full Analysis (Score + Summary + Questions)'),
            ('score_only', 'Score Only (Faster)'),
            ('questions_only', 'Generate Questions Only'),
        ],
        string='Analysis Mode',
        default='full',
        required=True,
    )
    progress_count = fields.Integer(
        string='Processed',
        readonly=True,
        default=0,
    )
    total_count = fields.Integer(
        string='Total',
        readonly=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Ready'),
            ('processing', 'Processing'),
            ('done', 'Done'),
        ],
        default='draft',
        readonly=True,
    )
    result_log = fields.Text(
        string='Results',
        readonly=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        if active_ids:
            res['applicant_ids'] = [(6, 0, active_ids)]
            res['total_count'] = len(active_ids)
        return res

    def action_start_bulk_scoring(self):
        """Process all selected applicants sequentially."""
        self.ensure_one()

        if not self.applicant_ids:
            raise UserError(_('No applicants selected.'))

        company = self.env.company
        if not company.ai_api_key:
            raise UserError(_(
                'AI API Key is not configured. '
                'Go to Settings → AI Recruitment to set it up.'
            ))

        results = []
        success_count = 0
        error_count = 0

        for idx, applicant in enumerate(self.applicant_ids, 1):
            try:
                if self.mode == 'questions_only':
                    applicant.action_ai_generate_questions()
                else:
                    applicant.action_ai_analyze()

                success_count += 1
                results.append(
                    f"✅ {applicant.partner_name or applicant.name or f'Applicant #{applicant.id}'}"
                    f" — Score: {applicant.ai_score:.0f}/100"
                )
            except Exception as e:
                error_count += 1
                results.append(
                    f"❌ {applicant.partner_name or applicant.name or f'Applicant #{applicant.id}'}"
                    f" — Error: {str(e)[:100]}"
                )
                _logger.error(
                    'Bulk AI scoring error for applicant %s: %s',
                    applicant.id, e,
                )

            # Update progress
            self.write({
                'progress_count': idx,
                'result_log': '\n'.join(results),
            })

        self.write({
            'state': 'done',
            'result_log': (
                f"=== Bulk AI Analysis Complete ===\n"
                f"Total: {len(self.applicant_ids)} | "
                f"Success: {success_count} | "
                f"Errors: {error_count}\n"
                f"{'=' * 40}\n\n"
                + '\n'.join(results)
            ),
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
