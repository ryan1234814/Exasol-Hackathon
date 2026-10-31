/* Service worker, hand-written — about seventy lines instead of a Workbox
 * dependency, because the project's rule is that the build stays installable
 * with no new packages.
 *
 * The cache policy is chosen for one specific risk: serving a stale bundle in
 * the middle of a demo. So navigation and /api are *network first* and only fall
 * back to the cache when the network genuinely fails; everything else (the
 * hashed assets) is stale-while-revalidate, which is safe because a new build
 * changes the filename.
 *
 * Bump CACHE_VERSION whenever the precache list changes. The activate handler
 * deletes every cache that does not carry the current name, so a bump is also
 * the repair path for a worker that got stuck.
 */
const CACHE_VERSION = 'wardq-v1'
const SHELL_CACHE = `${CACHE_VERSION}-shell`
const API_CACHE = `${CACHE_VERSION}-api`

// Deliberately short: '/' and '/index.html' plus the manifest and the two
// rendered icons. Hashed JS/CSS are not precached — they are picked up by the
// stale-while-revalidate rule on first use, so a rebuild cannot leave a
// precached hash pointing at a deleted file.
const PRECACHE = ['/', '/index.html', '/manifest.webmanifest', '/icon-192.png', '/icon-512.png']

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .catch(() => { /* a missing optional asset must not block the install */ })
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(
        names
          .filter((name) => !name.startsWith(CACHE_VERSION))
          .map((name) => caches.delete(name)),
      ))
      .then(() => self.clients.claim()),
  )
})

// Anything that writes passes straight through: /api/ingest/* and /api/classify
// are POSTs, and caching a POST response would be a lie about what was written.
self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return

  // Navigations: the network decides, the cache is only the parachute.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone()
          caches.open(SHELL_CACHE).then((cache) => cache.put('/index.html', copy)).catch(() => {})
          return response
        })
        .catch(() => caches.match('/index.html').then((hit) => hit || Response.error())),
    )
    return
  }

  // API reads: same rule, so a number is never older than the last successful
  // request unless the backend is actually unreachable.
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/feed/')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone()
            caches.open(API_CACHE).then((cache) => cache.put(request, copy)).catch(() => {})
          }
          return response
        })
        .catch(() => caches.match(request).then((hit) => hit || Response.error())),
    )
    return
  }

  // Assets: serve what we have, refresh in the background.
  event.respondWith(
    caches.match(request).then((hit) => {
      const network = fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone()
            caches.open(SHELL_CACHE).then((cache) => cache.put(request, copy)).catch(() => {})
          }
          return response
        })
        .catch(() => hit || Response.error())
      return hit || network
    }),
  )
})
