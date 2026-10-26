# Anabtawi Employee App API

Odoo 19 integration addon for the Anabtawi Employee App.

## Main features

- Employee App login endpoint with bearer token.
- Attendance, leave, overtime, and employee profile APIs.
- Single-device restriction for the Employee App only.
- Registered device, registered IP, last IP, registered date, and last login shown under the employee Settings tab.
- HR Manager can reset the Employee App device so the employee can register a different phone.
- Normal Odoo web login is not restricted and can still be used from multiple devices.

## Required existing addons

- `portal_check_in`
- `portal_leaves`
- `hr_attendance_overtime_approval_bridge`

## Installation / Upgrade

1. Replace the existing `anabtawi_mobile_api` folder in custom addons.
2. Push to Odoo.sh.
3. Upgrade **Anabtawi Employee App API** on staging.

Command-line example:

```bash
./odoo-bin -d ANABTAWI_DATABASE -u anabtawi_mobile_api --stop-after-init
```

## 19.0.1.7.0

- Added manager approval endpoints for the Employee App:
  - `GET  /anabtawi/mobile/manager/summary` (is_manager, pending counts)
  - `GET  /anabtawi/mobile/manager/leaves/pending`, `POST /anabtawi/mobile/manager/leaves/decision`
  - `GET  /anabtawi/mobile/manager/overtime/pending`, `POST /anabtawi/mobile/manager/overtime/decision`
- Team = employees whose Time Off approver (`leave_manager_id`) or manager (`parent_id.user_id`) is the caller. A caller can never decide on their own request.
- Time off: approve = first-level approval (`action_approve`); HR still validates in Odoo when the type uses two levels. Time Off officers can also give the second approval. Refuse needs a reason (posted to the chatter).
- Overtime: acts on the caller's pending approver line of `approval.request`.
- Fixed `NameError`: `os` was not imported, which broke `/anabtawi/mobile/apk/download` and `/pwa`.

## 19.0.1.7.1

- The wait between two check-in / check-out actions in the Employee App is now 2 minutes (was fixed at 10). Change it with the system parameter `anabtawi_mobile.attendance_lock_minutes`.

## 19.0.1.7.2

- Employees stay signed in: the session now renews itself while the app is used (sliding expiry, at most one write per day). Default lifetime is 365 days of inactivity (system parameter `anabtawi_mobile.token_ttl_days`, maximum 365).
- An expired session no longer unregisters the phone. Only the token is cleared, so the one-device rule still holds. HR reset and explicit sign-out behave as before.

## 19.0.1.7.3

- Check-in / check-out wait message now shows the real remaining seconds. A wait written under an older, longer setting is shortened to the current limit.

## 19.0.1.8.0

- `/anabtawi/mobile/apk/download` now streams the APK (with resume support) instead of loading it into memory.
- The app (Android APK, version 2.0.1 and later) checks `/anabtawi/mobile/app/check_update`: a dismissible banner when `latest_version` is newer, a blocking screen when the installed version is below `min_version` or `force_update` is true.
- The update settings (`anabtawi_mobile.latest_version`, `min_version`, `force_update`, `download_url`, `update_message`) are no longer reset when the module is upgraded. Edit them in Settings > Technical > System Parameters.

## 19.0.1.8.1

- Mandatory updates are enforced by the server for the Android app: when the installed version is below `anabtawi_mobile.min_version` (or below `latest_version` while `force_update` is True), login and every other request return `update_required` (HTTP 426). This also reaches builds older than 2.0.1, which cannot show the update screen. The app sends `X-App-Version` / `X-App-Platform` headers; older builds are judged by the version stored at login. Web and iPhone are never blocked.
