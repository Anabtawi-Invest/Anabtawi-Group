Employee App PWA 19.0.1.1.4

Static paths flattened to avoid Windows path-too-long extraction errors.


## 19.0.1.1.6
Based on the working 19.0.1.1.4 package.
Changes added without changing the working route/static structure:
- Hidden from Odoo Apps launcher; URL-only at /employee-portal.
- Mobile browser RTL/LTR stability fix.
- Arabic body direction fix.
- Added body dir sync when language changes.
- Service worker cache bumped.
- Profile image can use Odoo profile image URL when API returns it.


## 19.0.1.1.7
- Restored application=True so Odoo Apps can find and upgrade the module.
- Kept Employee App hidden from normal users using base.group_no_one instead of disabling the application.
- Added support for both /employee-portal and /employee-portal/ routes.
- Added sitemap=False to public PWA routes.


## 19.0.1.1.8
Mobile Arabic fix: keeps global document direction LTR to prevent React Native Web / iOS PWA horizontal clipping while Arabic labels remain handled by the app language layer.


## 19.0.1.4.0 (Employee App 1.3.0)
Rebuilt from source (`employee_app_mobile/`, build with `npm run web:build`).
- Check-in/out always takes a brand-new high-accuracy GPS fix (`maximumAge: 0`), no restart needed; sends accuracy and fix age; weak/denied/off states are re-checked when the app returns to the foreground.
- OTP countdown uses an absolute expiry (correct after the app was in the background); OTP never cached by the service worker.
- Manager approvals tab, notification bell with unread badge, cancel request, sick-leave attachment, payslip PDF share on native.
- Arabic/English and light/dark theme.
- Service worker: every `/anabtawi/mobile/*` endpoint outside the small read cache list is network-only.
