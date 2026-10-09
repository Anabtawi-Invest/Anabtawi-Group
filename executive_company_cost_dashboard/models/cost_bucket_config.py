# -*- coding: utf-8 -*-
import re
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class CeoCostBucket(models.Model):
    _name = "ceo.cost.bucket"
    _description = "Executive Cost & Profit Bucket"
    _order = "sequence, id"

    name = fields.Char(string="Bucket Name", required=True, translate=True)
    code = fields.Char(string="Code", required=True, index=True)
    category_type = fields.Selection([
        ("revenue", "Revenue / Top Line"),
        ("cogs", "Cost of Revenue / COGS"),
        ("expense", "Operating Expense / OpEx"),
    ], string="Financial Type", required=True, default="expense")
    color = fields.Char(string="Badge Color", default="#3b82f6")
    sequence = fields.Integer(string="Sequence", default=10)
    active = fields.Boolean(string="Active", default=True)
    mapping_ids = fields.One2many("ceo.cost.account.mapping", "bucket_id", string="Mapped Accounts")
    account_count = fields.Integer(string="Accounts Count", compute="_compute_account_count")

    @api.depends("mapping_ids")
    def _compute_account_count(self):
        for rec in self:
            rec.account_count = len(rec.mapping_ids)


class CeoCostAccountMapping(models.Model):
    _name = "ceo.cost.account.mapping"
    _description = "Account to Cost Bucket Mapping"
    _rec_name = "account_id"

    bucket_id = fields.Many2one("ceo.cost.bucket", string="Cost Bucket", required=True, ondelete="cascade", index=True)
    account_id = fields.Many2one("account.account", string="General Ledger Account", required=True, ondelete="cascade", index=True)
    account_code = fields.Char(related="account_id.code", string="Account Code", store=True)
    account_name = fields.Char(related="account_id.name", string="Account Name", store=True)
    company_ids = fields.Many2many("res.company", string="Companies", compute="_compute_company_ids")

    def _compute_company_ids(self):
        for rec in self:
            if hasattr(rec.account_id, "company_ids"):
                rec.company_ids = rec.account_id.company_ids
            elif hasattr(rec.account_id, "company_id"):
                rec.company_ids = rec.account_id.company_id
            else:
                rec.company_ids = False

    _sql_constraints = [
        ("unique_account_bucket", "unique(account_id)", "Each account can only be mapped to one cost bucket!")
    ]


class CeoSmartScannerWizard(models.TransientModel):
    _name = "ceo.smart.scanner.wizard"
    _description = "Smart Scanner for Auto-Mapping Accounts"

    overwrite_existing = fields.Boolean(string="Re-scan and Overwrite Existing Mappings", default=False)

    @staticmethod
    def _normalize_arabic(text):
        if not text:
            return ""
        text = str(text).lower()
        # Normalize alef variations
        text = re.sub(r"[إأآٱ]", "ا", text)
        # Normalize taa marbuta
        text = re.sub(r"ة", "ه", text)
        # Normalize yaa
        text = re.sub(r"ى", "ي", text)
        # Remove punctuation/symbols
        text = re.sub(r"[-_/\\().]", " ", text)
        return " ".join(text.split())

    def action_run_smart_scan(self):
        # Intelligent Scanner: matches accounts by code and normalized keywords in Arabic & English
        buckets = self.env["ceo.cost.bucket"].search([])
        bucket_by_code = {b.code: b for b in buckets}

        if not bucket_by_code:
            raise UserError(_("No cost buckets found. Please ensure initial data is loaded."))

        # Keyword matching dictionary
        rules = [
            ("RENT", ["ايجار", "عقود ايجار", "بدل ايجار", "rent", "lease", "occupancy", "store lease"]),
            ("UTILITIES", ["كهرباء", "مياه", "ماء", "محروقات", "سولار", "ديزل", "غاز", "electricity", "water", "utility", "generator", "fuel"]),
            ("PAYROLL", ["رواتب", "اجور", "ضمان", "تامين صحي", "مياومه", "اضافي", "مكافات", "بدل سكن", "نهايه خدمه", "غربه", "salary", "wage", "payroll", "allowance", "overtime", "social security"]),
            ("TECH", ["انترنت", "اتصالات", "هاتف", "برامج", "ايميل", "برمجيات", "تراخيص", "حاسوب", "تكنولوجيا", "internet", "telecom", "phone", "software", "license", "platform", "hosting", "email", "it"]),
            ("DELIVERY", ["طلبات", "كريم", "اشيائي", "كبسه", "توصيل", "شركات التوصيل", "talabat", "careem", "delivery", "aggregator"]),
            ("FLEET", ["سيارات", "مركبات", "شحن سيارات", "تتبع", "gps", "وقود مركبات", "vehicle", "fleet", "transport", "car"]),
            ("SECURITY", ["كاميرات", "حراسه", "امن", "مراقبه", "حمايه", "غرفه الحراسه", "security", "cctv", "surveillance", "guard", "civilian"]),
            ("MAINTENANCE", ["صيانه", "تصليح", "قطع غيار", "maintenance", "repair", "upkeep"]),
            ("LOSS", ["تالفه", "صلاحيه", "فروقات وزن", "عجز النقديه", "damaged", "expired", "shortage", "spoilage", "shrinkage"]),
            ("COGS", ["كلفه البضاعه", "تكلفه البضائع", "تعبئه وتغليف", "طبالي", "عينات", "جمركيه", "cogs", "cost of revenue", "packaging", "pallet"]),
            ("REVENUE", ["مبيعات", "ايراد", "sales", "revenue", "income"]),
        ]

        # Fetch accounts
        Account = self.env["account.account"]
        domain = []
        accounts = Account.search(domain)

        mapping_model = self.env["ceo.cost.account.mapping"]
        if self.overwrite_existing:
            mapping_model.search([]).unlink()

        existing_mapped_acc_ids = set(mapping_model.search([]).mapped("account_id.id"))

        created_count = 0
        for acc in accounts:
            if acc.id in existing_mapped_acc_ids:
                continue

            acc_code = str(acc.code or "").strip()
            norm_name = self._normalize_arabic(acc.name or "")
            matched_code = None

            # 1. Exact code pattern hints from Anabtawi chart
            if acc_code.startswith("6101") or acc.account_type == "income":
                matched_code = "REVENUE"
            elif acc_code.startswith("7301067") or acc.account_type == "expense_direct_cost":
                matched_code = "COGS"
            elif acc_code in ["7101021", "7301025"]:
                matched_code = "RENT"
            elif acc_code in ["7101027", "7301031", "7101029", "7301033", "7101036", "7301040"]:
                matched_code = "UTILITIES"
            elif acc_code in ["7101030", "7301034", "7101028", "7301032", "7101082", "7101090", "7101091"]:
                matched_code = "TECH"
            elif acc_code in ["7101073", "7101074", "7101075", "7101076", "7101057", "7101058"]:
                matched_code = "DELIVERY"
            elif acc_code in ["7101033", "7301037", "7101059", "7301042", "7101084"]:
                matched_code = "FLEET"
            elif acc_code in ["7101013", "7301017"]:
                matched_code = "SECURITY"
            elif acc_code in ["7101066", "7101067", "7101068", "7101054"]:
                matched_code = "LOSS"
            elif acc_code.startswith("5003") or acc_code in ["7101002", "7101003", "7101004", "7101072", "7301005"]:
                matched_code = "PAYROLL"

            # 2. Keyword fallback matching
            if not matched_code:
                for b_code, kw_list in rules:
                    if any(kw in norm_name for kw in kw_list):
                        matched_code = b_code
                        break

            # 3. Fallback for unclassified general expenses
            if not matched_code and (acc_code.startswith("71") or acc_code.startswith("73") or acc.account_type in ["expense", "expense_depreciation"]):
                matched_code = "OTHER_OPEX"

            if matched_code and matched_code in bucket_by_code:
                target_bucket = bucket_by_code[matched_code]
                mapping_model.create({
                    "bucket_id": target_bucket.id,
                    "account_id": acc.id,
                })
                existing_mapped_acc_ids.add(acc.id)
                created_count += 1

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Smart Scan Completed"),
                "message": _("Successfully scanned Chart of Accounts. Mapped %s accounts into Executive Buckets!") % created_count,
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            }
        }
