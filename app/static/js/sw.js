/* RestOS service worker: keeps the POS and kitchen display usable on flaky
 * restaurant Wi-Fi. Static assets are precached; operational pages use
 * network-first with cache fallback so a dropped connection shows the last
 * good screen instead of a browser error page. API calls are never cached
 * here — offline order queueing is handled in the POS page itself. */

const CACHE_VERSION = 'restos-v2';
const STATIC_CACHE = CACHE_VERSION + '-static';
const PAGES_CACHE = CACHE_VERSION + '-pages';

const PRECACHE_URLS = [
  '/static/css/main.css?v=17',
  '/static/fonts/fonts.css',
  '/static/vendor/htmx-1.9.12.min.js',
  '/static/vendor/chart-4.4.3.umd.min.js',
  '/static/js/notify.js?v=4',
  '/static/favicon.svg',
  '/static/favicon-192.png',
  '/static/manifest.json',
];

// Operational screens worth having offline (venue tablets stay logged in).
const OFFLINE_PAGES = ['/pos', '/kitchen', '/orders'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE_URLS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => !k.startsWith(CACHE_VERSION)).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return; // never interfere with mutations
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Static assets & fonts: cache-first (they're content-hashed/versioned)
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(STATIC_CACHE).then((c) => c.put(req, clone));
        }
        return res;
      }))
    );
    return;
  }

  // Operational pages: network-first, fall back to last good copy offline
  if (OFFLINE_PAGES.includes(url.pathname)) {
    event.respondWith(
      fetch(req).then((res) => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(PAGES_CACHE).then((c) => c.put(url.pathname, clone));
        }
        return res;
      }).catch(() => caches.match(url.pathname))
    );
    return;
  }
  // Everything else (API, partials): straight to network — freshness matters
  // more than availability, and the pages handle their own offline states.
});
