const CACHE = "anabtawi-employee-app-v1.2.0";
const SHELL = [
  "/employee-portal",
  "/employee-portal/manifest.webmanifest",
  "/anabtawi_employee_app_pwa/static/employee_app/app.js",
  "/anabtawi_employee_app_pwa/static/employee_app/favicon.ico",
  "/anabtawi_employee_app_pwa/static/employee_app/brand/logo.png",
  "/anabtawi_employee_app_pwa/static/employee_app/brand/symbol.png",
  "/anabtawi_employee_app_pwa/static/employee_app/icons/icon-192.png",
  "/anabtawi_employee_app_pwa/static/employee_app/icons/icon-512.png"
];
const API_CACHE_PATHS = [
  "/anabtawi/mobile/employee/profile",
  "/anabtawi/mobile/attendance/status",
  "/anabtawi/mobile/attendance/history",
  "/anabtawi/mobile/leaves/balances",
  "/anabtawi/mobile/leaves/list",
  "/anabtawi/mobile/overtime/categories",
  "/anabtawi/mobile/overtime/list",`n  "/anabtawi/mobile/payslips/list"
];
self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.pathname.startsWith("/odoo-proxy")) return;
  if (API_CACHE_PATHS.includes(url.pathname)) {
    event.respondWith(fetch(event.request).then((response) => {
      if (response.ok) {
        const copy = response.clone();
        void caches.open(CACHE).then((cache) => cache.put(event.request, copy));
      }
      return response;
    }).catch(() => caches.match(event.request).then((cached) => cached || new Response(JSON.stringify({ error: "offline", message: "Offline. Showing last synchronized data when available." }), { status: 503, headers: { "Content-Type": "application/json" } }))));
    return;
  }
  event.respondWith(fetch(event.request).then((response) => {
    if (response.ok && url.origin === self.location.origin) {
      const copy = response.clone();
      void caches.open(CACHE).then((cache) => cache.put(event.request, copy));
    }
    return response;
  }).catch(() => caches.match(event.request).then((cached) => cached || caches.match("/employee-portal"))));
});



