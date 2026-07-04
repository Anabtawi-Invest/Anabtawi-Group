const CACHE = "anabtawi-employee-app-staging-3cccf6f3091f";
const SHELL = [
  "/employee-portal",
  "/employee-portal/manifest.webmanifest",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/assets/brand/anabtawi-logo.4445484c88ec04405c70bf53aaecfcd5.png",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/assets/brand/anabtawi-symbol.01c436b8274c7bca8e40898f1cbd5230.png",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/AntDesign.3f78af31cca60105799838a1a7a59fbd.ttf",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/Entypo.31b5ffea3daddc69dd01a1f3d6cf63c5.ttf",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/EvilIcons.140c53a7643ea949007aa9a282153849.ttf",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/Feather.ca4b48e04dc1ce10bfbddb262c8b835f.ttf",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/FontAwesome.b06871f281fee6b241d60582ae9369b9.ttf",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/FontAwesome5_Brands.3b89dd103490708d19a95adcae52210e.ttf",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/FontAwesome5_Regular.1f77739ca9ff2188b539c36f30ffa2be.ttf",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/FontAwesome5_Solid.605ed7926cf39a2ad5ec2d1f9d391d3d.ttf",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/FontAwesome6_Brands.56c8d80832e37783f12c05db7c8849e2.ttf",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/FontAwesome6_Regular.370dd5af19f8364907b6e2c41f45dbbf.ttf",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/FontAwesome6_Solid.adec7d6f310bc577f05e8fe06a5daccf.ttf",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/Fontisto.b49ae8ab2dbccb02c4d11caaacf09eab.ttf",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/Foundation.e20945d7c929279ef7a6f1db184a4470.ttf",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/Ionicons.b4eb097d35f44ed943676fd56f6bdc51.ttf",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/MaterialCommunityIcons.6e435534bd35da5fef04168860a9b8fa.ttf",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/MaterialIcons.4e85bc9ebe07e0340c9c4fc2f6c38908.ttf",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/Octicons.871378c6eab492a3e689a9385dc45a12.ttf",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/SimpleLineIcons.d2285965fe34b05465047401b8595dd0.ttf",
  "/anabtawi_employee_app_pwa/static/employee_app/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/Zocial.1681f34aaca71b8dfb70756bca331eb2.ttf",
  "/anabtawi_employee_app_pwa/static/employee_app/favicon.ico",
  "/anabtawi_employee_app_pwa/static/employee_app/icons/favicon.png",
  "/anabtawi_employee_app_pwa/static/employee_app/icons/icon-192.png",
  "/anabtawi_employee_app_pwa/static/employee_app/icons/icon-512.png",
  "/anabtawi_employee_app_pwa/static/employee_app/icons/icon-64.png",
  "/anabtawi_employee_app_pwa/static/employee_app/index.html",
  "/anabtawi_employee_app_pwa/static/employee_app/manifest.webmanifest",
  "/anabtawi_employee_app_pwa/static/employee_app/metadata.json",
  "/anabtawi_employee_app_pwa/static/employee_app/_expo/static/js/web/AppEntry-671e9f26e4e329586045ad8a84bd85a1.js"
];
self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key.startsWith("anabtawi-employee-app-") && key !== CACHE).map((key) => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.pathname.startsWith("/anabtawi/mobile/")) return;
  event.respondWith(fetch(event.request).then((response) => {
    if (response.ok && url.origin === self.location.origin) {
      const copy = response.clone();
      event.waitUntil(caches.open(CACHE).then((cache) => cache.put(event.request, copy)));
    }
    return response;
  }).catch(() => caches.match(event.request).then((cached) => cached || caches.match("/employee-portal"))));
});
