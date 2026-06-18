/* WAKE Service Worker — v7 */
const SHELL_CACHE = "wake-shell-v7";
const DATA_CACHE  = "wake-data-v7";

const SHELL_URLS = [
  "/",
  "/index.html",
  "/manifest.json",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/apple-touch-icon.png",
  "/icons/favicon-32.png",
];

// Static reference data — cache aggressively, rarely changes
const STATIC_DATA = [
  "/fleet.json",
  "/ships.json",
  "/itineraries.json",
  "/ship_slugs.json",
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(SHELL_CACHE).then(c => c.addAll(SHELL_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== SHELL_CACHE && k !== DATA_CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const { url, method } = e.request;
  if (method !== "GET") return;

  const u = new URL(url);

  // Tile requests — network only (never cache map tiles)
  if (u.hostname.includes("tile") || u.pathname.includes("/tiles/")) return;

  // External APIs (weather, Wikipedia, AIS) — network only
  if (u.hostname !== self.location.hostname) return;

  // Serverless API routes — always network, never cache
  if (u.pathname.startsWith("/api/")) return;

  // Data files that update when we push — network first so new data is seen immediately
  if (u.pathname === "/deckplans.json") {
    e.respondWith(networkFirstShell(e.request));
    return;
  }

  // Live positions — network first, short-lived cache fallback
  if (u.pathname === "/positions.json") {
    e.respondWith(networkFirstShort(e.request));
    return;
  }

  // History files — stale-while-revalidate (updates daily)
  if (u.pathname.startsWith("/history/")) {
    e.respondWith(staleWhileRevalidate(e.request, DATA_CACHE));
    return;
  }

  // Static reference data — stale-while-revalidate
  if (STATIC_DATA.some(p => u.pathname === p)) {
    e.respondWith(staleWhileRevalidate(e.request, DATA_CACHE));
    return;
  }

  // index.html — always network first so updates are instant
  if(u.pathname === "/" || u.pathname === "/index.html"){
    e.respondWith(networkFirstShell(e.request));
    return;
  }

  // Other shell assets (icons, manifest) — cache first
  e.respondWith(cacheFirst(e.request));
});

async function networkFirstShell(req) {
  const cache = await caches.open(SHELL_CACHE);
  try {
    const res = await fetch(req);
    if(res.ok) cache.put(req, res.clone());
    return res;
  } catch {
    return await cache.match(req) || Response.error();
  }
}

async function cacheFirst(req) {
  const cached = await caches.match(req);
  if (cached) return cached;
  const res = await fetch(req);
  if (res.ok) {
    const cache = await caches.open(SHELL_CACHE);
    cache.put(req, res.clone());
  }
  return res;
}

async function staleWhileRevalidate(req, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(req);
  const fetchPromise = fetch(req).then(res => {
    if (res.ok) cache.put(req, res.clone());
    return res;
  }).catch(() => null);
  return cached || fetchPromise;
}

async function networkFirstShort(req) {
  const cache = await caches.open(DATA_CACHE);
  try {
    const res = await fetch(req);
    if (res.ok) {
      const clone = res.clone();
      // Only cache for 60s (let the next fetch refresh it)
      const headers = new Headers(clone.headers);
      headers.set("sw-cached-at", Date.now().toString());
      cache.put(req, new Response(await clone.blob(), { headers }));
    }
    return res;
  } catch {
    const cached = await cache.match(req);
    return cached || Response.error();
  }
}
