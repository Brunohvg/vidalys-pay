/* Vidalys Pay â€” Service Worker v4 */
const CACHE_NAME = 'vidalys-pay-v6';
const STATIC_ASSETS = [
  '/static/css/tokens.css',
  '/static/css/app.css',
  '/static/css/freight.css',
  '/static/css/pwa-install.css',
  '/static/js/app.js',
  '/static/js/pwa-install.js',
  '/static/js/push-notifications.js',
  '/static/brand/logo-symbol.svg',
  '/static/brand/logo-symbol-white.svg',
  '/static/pwa/app-icon-192.png',
  '/static/favicons/favicon-32.png',
  '/static/offline.html',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (request.method !== 'GET') return;

  // Never cache private/authenticated/api endpoints
  const noCachePrefixes = ['/api/', '/webhooks/', '/admin/', '/acesso/', '/painel/'];
  for (const prefix of noCachePrefixes) {
    if (url.pathname.startsWith(prefix)) {
      event.respondWith(fetch(request));
      return;
    }
  }

  // App pages: network first, fallback to offline
  if (url.pathname.startsWith('/app/')) {
    event.respondWith(
      fetch(request).catch(() => caches.match('/static/offline.html'))
    );
    return;
  }

  // Static assets: cache first, network fallback
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        if (response.ok && response.type === 'basic') {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        }
        return response;
      });
    })
  );
});
self.addEventListener('push', (event) => {
  let payload = {};
  try { payload = event.data ? event.data.json() : {}; } catch (_) {}
  const title = payload.title || 'Vidalys Pay';
  const options = {
    body: payload.body || 'Há uma atualização no seu pagamento.',
    icon: payload.icon || '/static/pwa/app-icon-192.png',
    badge: payload.badge || '/static/pwa/app-icon-192.png',
    tag: payload.tag || 'vidalys-payment-update',
    renotify: true,
    silent: false,
    vibrate: [180, 80, 180],
    data: {url: payload.url || '/app/historico/', eventType: payload.event_type || ''},
  };
  event.waitUntil(Promise.all([
    self.registration.showNotification(title, options),
    self.registration.setAppBadge ? self.registration.setAppBadge(1) : Promise.resolve(),
  ]));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || '/app/historico/', self.location.origin).href;
  event.waitUntil(
    clients.matchAll({type: 'window', includeUncontrolled: true}).then((windows) => {
      for (const client of windows) {
        if ('focus' in client) {
          client.navigate(target);
          return client.focus();
        }
      }
      return clients.openWindow ? clients.openWindow(target) : undefined;
    })
  );
});
