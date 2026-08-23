from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class OnlineCampaignCalendar(models.Model):
    _name = "online.campaign.calendar"
    _description = "Online Campaign Calendar"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_date desc, name, id"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    start_date = fields.Date(required=True, tracking=True, index=True)
    end_date = fields.Date(required=True, tracking=True, index=True)
    aggregator_id = fields.Many2one(
        "online.campaign.aggregator",
        string="Target Aggregator",
        tracking=True,
        check_company=True,
        index=True,
        help="Optional: restrict calendar to a specific aggregator, or leave empty for all aggregators.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("pending", "Waiting for Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )

    ecommerce_approved = fields.Boolean(readonly=True, copy=False, tracking=True)
    finance_approved = fields.Boolean(readonly=True, copy=False, tracking=True)
    ecommerce_approved_by = fields.Many2one("res.users", readonly=True, copy=False)
    ecommerce_approved_at = fields.Datetime(readonly=True, copy=False)
    finance_approved_by = fields.Many2one("res.users", readonly=True, copy=False)
    finance_approved_at = fields.Datetime(readonly=True, copy=False)

    pending_ecommerce_approved = fields.Boolean(readonly=True, copy=False, tracking=True)
    pending_finance_approved = fields.Boolean(readonly=True, copy=False, tracking=True)
    pending_ecommerce_approved_by = fields.Many2one("res.users", readonly=True, copy=False)
    pending_ecommerce_approved_at = fields.Datetime(readonly=True, copy=False)
    pending_finance_approved_by = fields.Many2one("res.users", readonly=True, copy=False)
    pending_finance_approved_at = fields.Datetime(readonly=True, copy=False)

    rejection_reason = fields.Text(tracking=True)
    note = fields.Text()

    campaign_ids = fields.One2many(
        "online.discount.campaign", "calendar_id", string="Campaigns"
    )

    has_pending_changes = fields.Boolean(
        compute="_compute_has_pending_changes",
        string="Has Pending Additions/Removals",
    )

    @api.depends("campaign_ids.state")
    def _compute_has_pending_changes(self):
        for calendar in self:
            calendar.has_pending_changes = any(
                campaign.state in ("pending_addition", "pending_removal")
                for campaign in calendar.campaign_ids
            )

    @api.constrains("start_date", "end_date")
    def _check_dates(self):
        for calendar in self:
            if calendar.start_date > calendar.end_date:
                raise ValidationError(_("Calendar start date must be before or equal to end date."))

    def action_submit(self):
        if self.filtered(lambda cal: cal.state != "draft"):
            raise UserError(_("Only draft campaign calendars can be submitted."))
        for calendar in self:
            if not calendar.campaign_ids:
                raise UserError(_("Add at least one campaign to the calendar before submitting for approval."))
            calendar.campaign_ids._check_ready_for_approval()
            calendar.write({
                "state": "pending",
                "ecommerce_approved": False,
                "finance_approved": False,
                "ecommerce_approved_by": False,
                "ecommerce_approved_at": False,
                "finance_approved_by": False,
                "finance_approved_at": False,
                "rejection_reason": False,
            })
            calendar.campaign_ids.write({
                "state": "pending",
                "ecommerce_approved": False,
                "finance_approved": False,
            })

    def _finalize_approval(self):
        for calendar in self:
            if calendar.state == "pending":
                if calendar.ecommerce_approved and calendar.finance_approved:
                    calendar.state = "approved"
                    calendar.campaign_ids.write({
                        "state": "approved",
                        "ecommerce_approved": True,
                        "finance_approved": True,
                        "ecommerce_approved_by": calendar.ecommerce_approved_by.id,
                        "ecommerce_approved_at": calendar.ecommerce_approved_at,
                        "finance_approved_by": calendar.finance_approved_by.id,
                        "finance_approved_at": calendar.finance_approved_at,
                    })
            elif calendar.state == "approved" and calendar.has_pending_changes:
                if calendar.pending_ecommerce_approved and calendar.pending_finance_approved:
                    # Approve additions
                    additions = calendar.campaign_ids.filtered(lambda c: c.state == "pending_addition")
                    additions.write({
                        "state": "approved",
                        "ecommerce_approved": True,
                        "finance_approved": True,
                        "ecommerce_approved_by": calendar.pending_ecommerce_approved_by.id,
                        "ecommerce_approved_at": calendar.pending_ecommerce_approved_at,
                        "finance_approved_by": calendar.pending_finance_approved_by.id,
                        "finance_approved_at": calendar.pending_finance_approved_at,
                    })
                    # Approve removals
                    removals = calendar.campaign_ids.filtered(lambda c: c.state == "pending_removal")
                    removals.write({
                        "state": "cancelled",
                        "ecommerce_approved": False,
                        "finance_approved": False,
                    })
                    calendar.write({
                        "pending_ecommerce_approved": False,
                        "pending_finance_approved": False,
                        "pending_ecommerce_approved_by": False,
                        "pending_ecommerce_approved_at": False,
                        "pending_finance_approved_by": False,
                        "pending_finance_approved_at": False,
                    })

    def action_ecommerce_approve(self):
        if not self.env.user.has_group("online_campaigns_discount.group_online_campaign_ecommerce_manager"):
            raise AccessError(_("Only an E-commerce Campaign Manager can give this approval."))
        now = fields.Datetime.now()
        for calendar in self:
            if calendar.state == "pending":
                calendar.campaign_ids._check_ready_for_approval()
                calendar.write({
                    "ecommerce_approved": True,
                    "ecommerce_approved_by": self.env.user.id,
                    "ecommerce_approved_at": now,
                })
            elif calendar.state == "approved" and calendar.has_pending_changes:
                pending_campaigns = calendar.campaign_ids.filtered(
                    lambda c: c.state in ("pending_addition", "pending_removal")
                )
                pending_campaigns._check_ready_for_approval()
                calendar.write({
                    "pending_ecommerce_approved": True,
                    "pending_ecommerce_approved_by": self.env.user.id,
                    "pending_ecommerce_approved_at": now,
                })
        self._finalize_approval()

    def action_finance_approve(self):
        if not self.env.user.has_group("online_campaigns_discount.group_online_campaign_finance_manager"):
            raise AccessError(_("Only an Online Campaign Finance Manager can give this approval."))
        now = fields.Datetime.now()
        for calendar in self:
            relevant_campaigns = calendar.campaign_ids
            if calendar.state == "approved" and calendar.has_pending_changes:
                relevant_campaigns = calendar.campaign_ids.filtered(
                    lambda c: c.state in ("pending_addition", "pending_removal")
                )
            missing_accounts = relevant_campaigns.filtered(
                lambda campaign: (campaign.aggregator_contribution_percent > 0 and not campaign.aggregator_id.receivable_account_id)
                or not campaign.aggregator_id.discount_expense_account_id
                or not campaign.aggregator_id.receivable_account_id
                or not campaign.aggregator_id.commission_expense_account_id
            )
            if missing_accounts:
                raise UserError(_(
                    "Configure the required aggregator receivable, company discount expense, and commission expense accounts before finance approval."
                ))

            if calendar.state == "pending":
                calendar.campaign_ids._check_ready_for_approval()
                calendar.write({
                    "finance_approved": True,
                    "finance_approved_by": self.env.user.id,
                    "finance_approved_at": now,
                })
            elif calendar.state == "approved" and calendar.has_pending_changes:
                relevant_campaigns._check_ready_for_approval()
                calendar.write({
                    "pending_finance_approved": True,
                    "pending_finance_approved_by": self.env.user.id,
                    "pending_finance_approved_at": now,
                })
        self._finalize_approval()

    def action_reject(self):
        if not self.env.user.has_group("online_campaigns_discount.group_online_campaign_approver"):
            raise AccessError(_("Only a campaign approver can reject calendars."))
        if self.filtered(lambda cal: not cal.rejection_reason):
            raise UserError(_("Enter a rejection reason before rejecting the calendar."))
        for calendar in self:
            if calendar.state == "pending":
                calendar.write({"state": "rejected"})
                calendar.campaign_ids.write({"state": "rejected"})
            elif calendar.state == "approved" and calendar.has_pending_changes:
                # Cancel pending additions, restore pending removals to approved
                calendar.campaign_ids.filtered(lambda c: c.state == "pending_addition").write({"state": "cancelled"})
                calendar.campaign_ids.filtered(lambda c: c.state == "pending_removal").write({"state": "approved"})
                calendar.write({
                    "pending_ecommerce_approved": False,
                    "pending_finance_approved": False,
                })

    def action_cancel(self):
        for calendar in self:
            calendar.write({"state": "cancelled"})
            calendar.campaign_ids.write({"state": "cancelled"})

    def action_reset_to_draft(self):
        if not self.env.user.has_group("online_campaigns_discount.group_online_campaign_approver"):
            raise AccessError(_("Only a campaign approver can reset calendars."))
        for calendar in self:
            calendar.write({
                "state": "draft",
                "ecommerce_approved": False,
                "finance_approved": False,
                "ecommerce_approved_by": False,
                "ecommerce_approved_at": False,
                "finance_approved_by": False,
                "finance_approved_at": False,
                "pending_ecommerce_approved": False,
                "pending_finance_approved": False,
            })
            calendar.campaign_ids.write({
                "state": "draft",
                "ecommerce_approved": False,
                "finance_approved": False,
            })
