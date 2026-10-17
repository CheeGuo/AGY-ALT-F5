// Pelita service worker: the app shell and the offline study pack load from cache
// first (instant on 2G, works with no signal), then refresh in the background.
var CACHE = "pelita-v1";
var SHELL = ["/", "/manifest.webmanifest", "/icon.svg"];

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(SHELL); }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (e) {
  var url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== self.location.origin || url.pathname === "/sw.js") return;
  e.respondWith(caches.open(CACHE).then(function (cache) {
    return cache.match(e.request).then(function (hit) {
      var fresh = fetch(e.request).then(function (res) {
        if (res.ok) cache.put(e.request, res.clone());
        return res;
      }).catch(function () { return hit || cache.match("/"); });
      return hit || fresh;
    });
  }));
});
