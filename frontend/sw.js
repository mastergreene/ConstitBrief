/* Moreton Casework service worker.
 * - App shell: precached, served cache-first (updated in the background).
 * - /api/meta and GET /api/templates: network-first, cached for offline use (no PII).
 * - Everything else under /api (triage, cases, drafts): network only, never cached,
 *   because it can contain constituent information.
 */
const VERSION = 'v1.0.0';
const SHELL = `shell-${VERSION}`;
const DATA = `data-${VERSION}`;
const SHELL_FILES = [
  '/', '/index.html', '/css/app.css', '/manifest.webmanifest',
  '/js/app.js', '/js/api.js', '/js/store.js', '/js/jotform.js', '/js/requirements.js', '/js/speech.js',
  '/icons/icon-192.png', '/icons/icon-512.png', '/icons/apple-touch-icon.png',
];
const CACHEABLE_API = ['/api/meta', '/api/templates'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(SHELL).then((c) => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== SHELL && k !== DATA).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

function offlineJson() {
  return new Response(JSON.stringify({ detail: 'Offline' }), {
    status: 503, headers: { 'Content-Type': 'application/json', 'X-Offline': '1' },
  });
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // Jotform, gov sites: straight to network

  if (url.pathname.startsWith('/api/')) {
    if (req.method === 'GET' && CACHEABLE_API.includes(url.pathname)) {
      event.respondWith(
        fetch(req)
          .then((res) => {
            if (res.ok) { const copy = res.clone(); caches.open(DATA).then((c) => c.put(req, copy)); }
            return res;
          })
          .catch(() => caches.match(req).then((hit) => hit || offlineJson())),
      );
    } else {
      event.respondWith(fetch(req).catch(() => offlineJson()));
    }
    return;
  }

  if (req.method !== 'GET') return;

  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).catch(() => caches.match('/index.html')));
    return;
  }

  // Stale-while-revalidate for the shell.
  event.respondWith(
    caches.match(req).then((hit) => {
      const net = fetch(req).then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(SHELL).then((c) => c.put(req, copy)); }
        return res;
      }).catch(() => hit);
      return hit || net;
    }),
  );
});
