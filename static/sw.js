/* Vidalys Pay — Service Worker v2 */
const CACHE_NAME = 'vidalys-pay-v2';
const STATIC_ASSETS = [
  '/',
  '/static/css/tokens.css',
  '/static/css/app.css',
  '/static/js/app.js',
  '/static/manifest.webmanifest',
  '/static/brand/icons/favicon.svg',
  '/static/offline.html',
];

// Install — cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate — clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch — network first for API, cache first for static
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET
  if (request.method !== 'GET') return;

  // Never cache API or webhook responses
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/webhooks/')) {
    event.respondWith(fetch(request));
    return;
  }

  // Never cache authenticated pages (app shell only via cache)
  if (url.pathname.startsWith('/app/') || url.pathname.startsWith('/admin/')) {
    event.respondWith(
      fetch(request).catch(() => caches.match('/static/offline.html'))
    );
    return;
  }

  // Static assets — cache first
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        }
        return response;
      });
    })
  );
});
