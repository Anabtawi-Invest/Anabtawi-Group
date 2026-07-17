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

Run the automated tests:

```bash
python D:\odoo-19.0\odoo-19.0\odoo-bin -d <test_database> -i ai_reporting --test-enable --test-tags ai_reporting --stop-after-init --addons-path=D:\odoo-19.0\odoo-19.0\addons,D:\Ai Reporting
```

## Fixes applied in this review pass

This module already existed from an earlier session (see git history / file timestamps under
`D:\Ai Reporting\ai_reporting`). This pass re-verified it against the real Odoo 19.0 source at
`D:\odoo-19.0\odoo-19.0` (not just general Odoo knowledge, since Odoo 19 renamed several core
fields) and fixed the following:

- **Fabricated model name removed.** `openai_model` defaulted to the non-existent `"gpt-5.6-terra"`
  in `models/res_config_settings.py`, `data/ir_config_parameter.xml`, and
  `services/third_party_ai_provider.py`. It now defaults to empty and `_call_openai` raises a clear
  `UserError` if an admin enables the OpenAI provider without setting a real model name. (Anthropic's
  default, `claude-sonnet-5`, was verified accurate and left as-is.)
- **OWL `rpc` breaking change.** `static/src/js/report_builder.js` used `useService("rpc")`, which
  was removed when Odoo moved the rpc helper to a plain function in `@web/core/network/rpc` (verified
  against `addons/web/static/src/core/network/rpc.js` in the Odoo 19 source — there is no `"rpc"`
  entry in the services registry). Fixed to `import { rpc } from "@web/core/network/rpc"`.
- **Share permission enforcement.** `ai.reporting.saved.report` granted model-level write/create to
  the base User group (so owners can manage their own reports), but any user who could merely *see*
  a company/global/shared report (via `ir.rule`) could also edit or delete it — sharing "View and Run"
  did not actually restrict to view-and-run. Added `write()`/`unlink()` overrides that check the
  `ai.reporting.saved.report.share` permission level (owner or manager bypass; `edit`/`manage` required
  to write, `manage` required to unlink), with a narrow carve-out so `action_run()`'s own bookkeeping
  fields (`last_refresh_date`, etc.) stay writable by a run-only share.
- **Owners could not self-serve sharing.** `ai.reporting.saved.report.share` was manager-only at the
  ACL level, so an owner could not share their own report without a manager. Granted the User group
  create/write/unlink and added an `ir.rule` restricting it to `report_id.owner_id == user` (or manager).
- **Multi-company isolation was missing.** `allowed_company_ids`/`company_id` fields existed on
  `ai.reporting.memory`, `ai.reporting.request`, and `ai.reporting.saved.report`, but no `ir.rule`
  ever read them — a global/company-visible record from another company was visible to any user.
  Added company-scoped rules (`domain_force` using the standard Odoo `company_ids` rule variable,
  matching the pattern in `addons/analytic/security/analytic_security.xml`).
- **`maximum_date_range` setting was unused.** It appeared in Settings but no code ever read it.
  Added a post-resolution check in `query_execution_service.execute_plan` that rejects a resolved
  domain whose date-range span (same field, `>=`/`<=` pair) exceeds the configured number of days.
- **Settings menu now deep-links.** `Configuration` pointed at the generic
  `base_setup.action_general_configuration` (the whole Settings app). Added a dedicated
  `res.config.settings` action with `context={'module': 'ai_reporting'}` so it opens directly on the
  AI Reporting tab, matching the pattern used by `addons/crm/views/res_config_settings_views.xml`.
- Added tests for all of the above (share-permission bypass, owner self-service sharing implied by
  the fix, date-range rejection, multi-company isolation).

Everything else — the models, the JSON-schema plan validator (blocks SQL/eval/sudo/unbounded limits),
the parameter resolver (no `eval`, allowlisted `$placeholders` only), the ORM-only query execution
(no `sudo()` anywhere in the codebase), the local-memory exact/parameterized/phrase matching, the
discovery service that generates reusable query templates from whatever models are actually installed,
and the confirm-before-save Advanced Report flow — was already implemented correctly and is unchanged.

## Native Ask AI integration (verified against your real server)

`D:\Anabtawi-Group-main` never contained Odoo Enterprise, so the native bridge originally had nothing
real to connect to. That changed once your Odoo.sh production shell became available in this session:
I found the actual Enterprise `ai` app source at `/home/odoo/src/enterprise/ai` on
`reyadkhuffash-anabtawi-group-main-26608062` (technical name `ai`, wrapped by the installable app
`ai_app`) and read the real model code rather than guessing. Confirmed facts, not assumptions:

- "AI Tools" are plain `ir.actions.server` records with `state='code'`, `use_in_ai=True`,
  `ai_tool_description` (text) and `ai_tool_schema` (a JSON string: `{"properties": {...}, "required": [...]}`).
  The tool's `code` runs with `env`/`model`/`record` bound to the *non-sudo* caller and must set
  `ai['result'] = ...` (confirmed in `ir_actions_server.py`'s `_ai_tool_run`).
- `ai.topic` (fields: `name`, `description`, `instructions`, `tool_ids`) groups tools with instructions
  for the agent.
- `ai.agent.topic_ids` attaches topics to an agent, and `ai.ai_default_agent` is a real, stable XML ID
  for the default Ask AI agent shipped by the module.

`services/odoo_ai_bridge.py` now acts on this: `_native_ai_app_ready()` checks every one of those
fields actually exists before touching anything (so a future Odoo version that changes this shape
degrades to "not available" instead of guessing), and `_register_native_ai_tools()` idempotently
creates/updates three tool actions (list reports, run a report by id, draft a report from a question),
groups them under one `ai.topic` named "AI Reporting: Advanced Reports", and attaches that topic to
`ai.ai_default_agent` if present. This runs from `register_integration()`, which is called by
`post_init_hook` (on install), the existing daily `ir_cron_ai_reporting_discovery` cron, and can be
re-run anytime via `env["ai.reporting.odoo_ai_bridge"].register_integration()` in an Odoo shell.

The three tools call the same `_ai_tool_list_reports` / `_ai_tool_run_report` /
`_ai_tool_create_advanced_report` methods added to `ai.reporting.saved.report` and
`ai.reporting.request` — the same methods also carry the OCA `ai_tool` decorator (see below) so they
work either way, with no code duplicated between the two integrations.

**One nuance I could not fully verify from source alone**: which Odoo user's permissions apply when
the agent executes a tool's `code` (the actual chatting human, vs. some fixed service/agent account).
Our tool code calls `search()`/normal ORM through `model.env`, so whatever user that env resolves to
determines what reports it can see and run — please verify this once installed by asking the agent to
list/run a report as a non-admin user and confirming it only sees reports that user should see.

After installing on your production/staging database (where `ai`/`ai_app` are already present), check
Settings > Technical > AI > Agents, open the default agent, and confirm "AI Reporting: Advanced
Reports" appears under its Topics — then anyone chatting with that agent can ask it to list, run, or
draft your Advanced Reports.

## Local Memory interception for ordinary Ask AI questions (`ai_reporting_ai_bridge`)

The tool-registration above only covers Advanced Reports. Ordinary business questions typed into
native Ask AI (e.g. "sales for Downtown Branch from June to July") were still going straight to
Odoo's own LLM connection with no Local Memory check at all — that gap is what a second addon,
`ai_reporting_ai_bridge`, closes.

This had to be a **separate addon**, not code inside `ai_reporting` itself, because it needs
`_inherit = "ai.agent"`, and `ai.agent` only exists on databases where the real Enterprise `ai` app
is installed. Putting that class directly in `ai_reporting` would crash installation on any database
without that app. `ai_reporting_ai_bridge` instead declares `"depends": ["ai_reporting", "ai"]` and
`"auto_install": True` — the standard Odoo pattern for optional glue modules (same pattern as core's
own `sale_stock`) — so it only ever installs itself once both are present, and never loads (so never
references `ai.agent`) otherwise.

It overrides `ai.agent._generate_response_for_channel(mail_message, channel)`, which I verified is
the real per-chat-message entry point in `/home/odoo/src/enterprise/ai/models/ai_agent.py` on your
own Odoo.sh instance: it parses the user's prompt, calls `_generate_response()` (which is what
actually calls the configured LLM provider and is what was demanding an API key), then posts each
returned string back to the channel via `_post_ai_response()`. The override checks AI Reporting's
Local Memory for the parsed prompt *before* calling `super()`; on a confirmed match it formats the
result as a small markdown table and posts it directly, skipping the LLM call (and any API key
requirement) entirely for that question. On any non-match or internal error it falls straight through
to `super()._generate_response_for_channel(...)`, so native Ask AI behaves exactly as it did before
this addon existed. Gated by the existing `enable_native_ask_ai_lma` setting (Settings > AI
Reporting), default on.

`services/odoo_ai_bridge.format_local_memory_chat_reply(question, result)` builds the markdown reply
and lives in `ai_reporting` (not the glue addon) specifically so it can be unit tested
(`test_format_local_memory_chat_reply_renders_markdown_table` /
`..._handles_empty_rows` in `tests/test_ai_reporting.py`) without the real `ai` app installed.

## Discovery: relative periods, by-branch breakdowns, and comparisons

The Discovery wizard (`services/discovery_service.py`) generates a much broader set of ready-to-use
Local Memory questions, not just fixed-date-range templates. `_relative_periods()` defines ten named
ranges (today, yesterday, this/last week, this/last month, this/last quarter, this/last year), each
resolved server-side at run time by `services/parameter_resolver.py` (`$month_start(report_date)` and
friends), so a saved phrase like "sales last quarter" never goes stale — it recomputes the real
quarter boundaries every time it runs, not the boundaries from whenever it was generated.

For sales, purchases, and vendor bills, `_period_and_comparison_templates()` builds, per period: a
total (e.g. "how much sales this month"), a by-branch breakdown if the model has a branch/warehouse/
company field (e.g. "sales by branch this month"), and month-over-month / quarter-over-quarter /
year-over-year comparisons (e.g. "compare sales between this month and last month"). Comparisons use
a new `plan_type: "comparison"` plan shape (`domain_a`/`domain_b`/`label_a`/`label_b`) that reuses the
existing single-domain validator and executor twice — once per side — so a comparison plan never
bypasses the same SQL/eval/sudo/unbounded-limit checks a normal plan goes through
(`query_execution_service.execute_comparison`).

Every other installed model that has a date field and a numeric field also gets a smaller, bounded set
(this month / last month / one comparison, plus a by-branch breakdown if applicable) via
`_generic_relative_period_templates()`, so "how much `<anything>` this month" works across the whole
database without generating an unbounded number of Local Memory records per model.

Example phrases now answerable straight from Local Memory (no AI/API key needed) once Discovery has
run: "sales this month", "sales by branch last quarter", "compare sales between this month and last
month", "purchases last year", "vendor bills by branch this week", "compare purchases between this
quarter and last quarter". Native Ask AI questions matching a comparison template are formatted by
the new `odoo_ai_bridge.format_local_memory_comparison_reply()` as a small markdown table with
per-measure totals and percentage change.

## What is intentionally out of scope for this pass
- **OCA `ai_oca_bridge`**: inspected for architectural reference only, per instruction, and not used
  or copied — `odoo_ai_bridge.py` and `third_party_ai_provider.py` are this module's own code.
- **True multilingual embeddings**: `embedding_service.py` uses a deterministic hash-based fallback
  (`health_check()` reports `backend: "local_hash_fallback"` honestly) rather than a real embedding
  model, and Arabic/English semantic matching relies on the phrase-normalization + exact-hash matching
  in `ai_reporting_memory.py`, not vector similarity.
- **No live Odoo/Postgres instance in this session's sandbox.** Verification this pass was: every
  `.py` file compiles (`py_compile`), every `.xml` file is well-formed, the manifest's `data`/`assets`
  paths all resolve to real files, every `ir.model.access.csv` and `ir.rule` `model_id` reference
  resolves to a real `_name`, and every menu `action` reference resolves to a real action id. Field
  names used against core Odoo (`res.groups.user_ids`, `res.users.group_ids`,
  `res.groups.privilege_id`/`res.groups.privilege`, `fields.Json`, `Manifest.for_addon`, `has_access`,
  `read_group` signature, the settings `<app>` inheritance pattern) were checked against the real
  Odoo 19.0 source at `D:\odoo-19.0\odoo-19.0`, not assumed from general Odoo knowledge — this matters
  because Odoo 19 renamed several of these from older versions. The automated test suite in `tests/`
  was written and reviewed but not executed against a live database; run the test command above on
  your real instance before deploying.
