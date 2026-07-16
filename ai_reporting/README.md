# AI Reporting

AI Reporting is an Odoo 19 addon that adds a local-memory layer for business-data Ask AI questions and a separate confirmed Advanced Report Builder.

Detected references used during creation:

- Odoo server root: `D:\odoo-19.0\odoo-19.0`
- Odoo version: `19.0`
- Community addons: `D:\odoo-19.0\odoo-19.0\addons`
- Custom addon convention reference: `D:\Anabtawi-Group-main\Anabtawi-Group-main`
- Output addon path: `D:\Ai Reporting\ai_reporting`

The inspected Community checkout includes website/editor AI text helpers, but not the native business Ask AI source described in the master prompt. The bridge therefore detects native AI models at runtime and uses a direct third-party provider when configured.

Third-party AI provider:

- Select `OpenAI` or `Claude / Anthropic` in Settings > AI Reporting.
- API keys are not stored in Odoo. The module reads the environment variable named in settings.
- Default environment variable names are `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`.
- The AI provider only drafts JSON report definitions. Odoo validates models, fields, domains, limits, and access before execution.
- Saved reports run deterministically without calling the AI provider again.
- Local Memory stores reusable query templates, not only finished answers. A memory phrase can use placeholders such as `sales for {branch}` and a plan domain can use parameters such as `$branch_id` or `$branch_name`; when a user asks for another branch, Odoo resolves the new parameter and executes the saved query plan with fresh data.
- The Discovery wizard scans installed addons through Odoo manifests and installed models through `ir.model`. It builds targeted business templates plus generic templates for every readable installed model. Generic templates are created only when a model has safe fields for date ranges, branches/companies, partners, products, status, numeric totals, min/max values, or top grouped records.

Recommended production path:

1. Set `third_party_provider` to `anthropic` for complex report design or `openai` for a broad general-purpose provider.
2. Set the matching API key environment variable on the Odoo server process.
3. Keep the report confirmation requirement enabled so users approve the exact definition before saving.

Install with an addons path that includes this folder:

```bash
python D:\odoo-19.0\odoo-19.0\odoo-bin -d <database> -i ai_reporting --addons-path=D:\odoo-19.0\odoo-19.0\addons,D:\Ai Reporting
```

Update:

```bash
python D:\odoo-19.0\odoo-19.0\odoo-bin -d <database> -u ai_reporting --addons-path=D:\odoo-19.0\odoo-19.0\addons,D:\Ai Reporting
```
