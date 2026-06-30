const CACHE = "jam-v4";
const ASSETS = [
  "/",
  "/host",
  "/play",
  "/static/css/style.css",
  "/static/js/host.js",
  "/static/js/player.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/sounds/buzz.mp3",
  "/manifest.json"
];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== CACHE).map(k => caches.delete(k))
    ))
  );
  self.clients.claim();
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  
  // bypass sw for sockets
  if (url.pathname.startsWith("/socket.io") || url.hostname !== self.location.hostname) return;

  e.respondWith(
    fetch(e.request)
      .then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
