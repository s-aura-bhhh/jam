// service-worker.js
// Uses a Network-First strategy so you never get stuck with old code.

const CACHE_NAME = "jam-buzzer-v4";

const SHELL = [
  "/",
  "/host",
  "/play",
  "/static/css/style.css",
  "/static/js/host.js",
  "/static/js/player.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/manifest.json",
];

// ---- install: cache the shell ----
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL))
  );
  self.skipWaiting();
});

// ---- activate: clean up old caches ----
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// ---- fetch: NETWORK-FIRST STRATEGY ----
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Always bypass Service Worker for Socket.IO
  if (url.pathname.startsWith("/socket.io") || url.hostname !== self.location.hostname) {
    return;
  }

  // Network-First, fallback to Cache
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        // If we get a good response, save a copy to the cache for later
        return caches.open(CACHE_NAME).then((cache) => {
          cache.put(event.request, networkResponse.clone());
          return networkResponse;
        });
      })
      .catch(() => {
        // If the network fails (offline), load from the cache
        return caches.match(event.request);
      })
  );
});