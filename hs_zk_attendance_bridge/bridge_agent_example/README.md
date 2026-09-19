# Attendance Bridge Agent

Local agent that reads attendance punches and pushes them to the existing Odoo
endpoint:

`POST /hs_zk_attendance_bridge/push`

Odoo still owns employee mapping, duplicate handling, and Check In / Check Out
pairing. This agent does not redesign the Odoo module.

## Sources

| `SOURCE_TYPE` | Reader | Notes |
|---|---|---|
| `zk` | ZK device via `pyzk` | Original behavior |
| `sql` | SQL Server table | Incremental by `log_id` |

## Install

```bash
cd bridge_agent_example
python3 -m pip install -r requirements.txt
```

For SQL Server you also need an ODBC driver on the machine, for example
**ODBC Driver 18 for SQL Server**.

## Shared environment

- `ODOO_URL`: Odoo base URL, for example `https://my-db.odoo.com`
- `BRIDGE_TOKEN`: token from **Attendances → Biometric Bridge → Bridge Devices**
- `DEVICE_TIMEZONE`: device/local timezone, for example `Asia/Amman`
- `SYNC_INTERVAL`: seconds between cycles, default `60`
- `RUN_ONCE=1`: run one cycle and exit
- `SOURCE_TYPE`: `zk` or `sql`

## ZK mode

```bash
export SOURCE_TYPE=zk
export ODOO_URL="https://my-db.odoo.com"
export BRIDGE_TOKEN="paste-token-here"
export DEVICE_IP="192.168.100.64"
export DEVICE_PORT="4372"
export DEVICE_TIMEZONE="Asia/Amman"
python3 agent.py
# or: python3 zk_bridge_agent.py
```

## SQL Server mode

Default table name: `attenendad`

Expected columns:

- `log_id`
- `machine_id`
- `empCode`
- `TrxType` (ignored for In/Out)
- `TrxDateTime`

### Windows Authentication (recommended on the local DB PC)

No `SQL_USER` / `SQL_PASSWORD`. The script uses the Windows account that runs it.

```bash
export SOURCE_TYPE=sql
export ODOO_URL="https://my-db.odoo.com"
export BRIDGE_TOKEN="paste-token-here"
export DEVICE_TIMEZONE="Asia/Amman"

export SQL_AUTH=windows
export SQL_HOST=localhost
export SQL_PORT=1433
export SQL_DATABASE="your_database_name"
export SQL_TABLE=attenendad
export SQL_DRIVER="ODBC Driver 18 for SQL Server"

python3 sql_bridge_agent.py
```

If SSMS shows a named instance such as `.\SQLEXPRESS`, use:

```bash
export SQL_HOST="localhost\\SQLEXPRESS"
```

### SQL Login (optional)

Only if you already have a SQL username/password:

```bash
export SQL_AUTH=sql
export SQL_USER="existing_user"
export SQL_PASSWORD="existing_password"
```

### Incremental sync

1. Read `last_log_id` from `STATE_FILE` (default `state.json`)
2. Select rows with `log_id > last_log_id`
3. Order by `TrxDateTime ASC, log_id ASC`
4. Push to Odoo using the same JSON schema as the ZK agent
5. Update `last_log_id` only after Odoo accepts the batch

If Odoo fails, the cursor is not advanced. Re-sending is safe because Odoo
deduplicates punches.

### Mapping to Odoo

- SQL `empCode` → Odoo payload `device_user_id`
- Employee in Odoo must have the same value in **Biometric Device ID**
- First punch = Check In, second = Check Out, third = Check In, ... handled by Odoo

Do not put passwords or tokens into source code. Use environment variables.
