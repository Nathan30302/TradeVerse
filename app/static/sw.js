/* PWA install shell + light offline static cache (HTML still network-first). */
const TV_STATIC_CACHE = 'tv-static-v1';
const TV_PRECACHE = [
  '/static/css/style.css',
  '/static/css/mobile-nav.css',
  '/static/js/motivational-quotes.js',
  '/static/img/default-avatar.svg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(TV_STATIC_CACHE).then((cache) => cache.addAll(TV_PRECACHE).catch(() => undefined))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== TV_STATIC_CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  // Only cache-first for static assets; never intercept authenticated HTML/API.
  if (!url.pathname.startsWith('/static/')) return;
  event.respondWith(
    caches.match(req).then((cached) => {
      const network = fetch(req)
        .then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(TV_STATIC_CACHE).then((c) => c.put(req, copy)).catch(() => undefined);
          }
          return res;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});
