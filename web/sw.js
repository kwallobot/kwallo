// Kwallo service worker (v36): makes the site installable and lets it open without a connection, showing the last matches
// it loaded. Everything is fetched fresh when there's a connection (network first); the saved copies are only the fallback.
// A new version of this file takes over the next time the app is opened (the old saved copies are then cleared).
const VERSION = "kwallo-v37d-1";
const SHELL = `shell-${VERSION}`, DATA = "data-v1", FONTS = "fonts-v1";
const SHELL_FILES = ["/", "/app.js", "/style.css", "/config.js", "/logo.svg", "/icon-192.png", "/manifest.webmanifest"];   // ("/index.html" redirects to "/")
const DATA_MAX = 200;                                            // saved data files kept (oldest dropped first)

self.addEventListener("install", e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(SHELL_FILES)).catch(() => {}));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith("shell-") && k !== SHELL).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

async function trim(name, max) {
  const c = await caches.open(name), keys = await c.keys();
  for (const k of keys.slice(0, Math.max(0, keys.length - max))) await c.delete(k);
}
// fresh from the network, saving a copy; the saved copy if the network fails
async function networkFirst(req, cacheName, fallbackUrl) {
  const c = await caches.open(cacheName);
  try {
    const res = await fetch(req);
    if (res && res.ok && !res.redirected) {
      c.put(req, res.clone()).then(() => cacheName === DATA && trim(DATA, DATA_MAX)).catch(() => {});
    }
    return res;
  } catch (err) {
    const hit = (await c.match(req, { ignoreSearch: cacheName === SHELL })) || (fallbackUrl && (await caches.match(fallbackUrl)));
    if (hit) return hit;
    throw err;
  }
}
async function cacheFirst(req, cacheName) {
  const c = await caches.open(cacheName), hit = await c.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res && (res.ok || res.type === "opaque")) c.put(req, res.clone()).catch(() => {});
  return res;
}

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;                              // e.g. the page-visit counter
  const url = new URL(req.url);
  if (url.origin === self.location.origin) {
    if (req.mode === "navigate") return e.respondWith(networkFirst(req, SHELL, "/"));
    return e.respondWith(networkFirst(req, SHELL));
  }
  if (/\/api\/(site|result|live|transfers)/.test(url.pathname)) return e.respondWith(networkFirst(req, DATA));   // the Worker's data
  if (url.hostname === "fonts.googleapis.com" || url.hostname === "fonts.gstatic.com") return e.respondWith(cacheFirst(req, FONTS));
});
