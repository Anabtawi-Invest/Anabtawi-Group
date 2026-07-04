const CACHE = "anabtawi-employee-app-v1";
const SHELL = [
  "/employee-portal",
  "/employee-portal/manifest.webmanifest",
  "/anabtawi_employee_app_pwa/static/employee_app/favicon.ico",
  "/anabtawi_employee_app_pwa/static/employee_app/icons/icon-192.png",
  "/anabtawi_employee_app_pwa/static/employee_app/icons/icon-512.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET") return;
  if (url.pathname.startsWith("/anabtawi/mobile/")) return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok && url.origin === self.location.origin) {
          const copy = response.clone();
          event.waitUntil(caches.open(CACHE).then((cache) => cache.put(event.request, copy)));
        }
        return response;
      })
      .catch(() => caches.match(event.request).then((cached) => cached || caches.match("/employee-portal")))
  );
});
