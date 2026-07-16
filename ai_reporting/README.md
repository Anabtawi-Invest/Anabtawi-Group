# AI Reporting

AI Reporting is an Odoo 19 addon that adds a local-memory layer for business-data Ask AI questions and a separate confirmed Advanced Report Builder.

Detected references used during creation:

- Odoo server root: `D:\odoo-19.0\odoo-19.0`
- Odoo version: `19.0`
- Community addons: `D:\odoo-19.0\odoo-19.0\addons`
- Custom addon convention reference: `D:\Anabtawi-Group-main\Anabtawi-Group-main`
- Output addon path: `D:\Ai Reporting\ai_reporting`

The inspected Community checkout includes website/editor AI text helpers, but not the native business Ask AI source described in the master prompt. The bridge therefore detects native AI models at runtime and fails gracefully when they are unavailable.

Optional OCA AI support:

- If OCA AI modules such as `ai_connection`, `ai_oca_bridge`, or `ai_tool` are installed, `ai_reporting` detects the runtime models `ai.connection`, `ai.bridge`, and `ai.tool`.
- When an active `ai.connection` exists, AI Reporting can use it as an optional Ask AI provider path for ordinary answers and Advanced Report draft JSON generation.
- OCA AI support is optional and does not add a hard dependency, so the module still installs on plain Odoo 19.
- OCA AI is not the same as Odoo Enterprise native Ask AI; it is a useful compatibility bridge until the Enterprise Ask AI source/API is available.

Install with an addons path that includes this folder:

```bash
python D:\odoo-19.0\odoo-19.0\odoo-bin -d <database> -i ai_reporting --addons-path=D:\odoo-19.0\odoo-19.0\addons,D:\Ai Reporting
```

Update:

```bash
python D:\odoo-19.0\odoo-19.0\odoo-bin -d <database> -u ai_reporting --addons-path=D:\odoo-19.0\odoo-19.0\addons,D:\Ai Reporting
```
