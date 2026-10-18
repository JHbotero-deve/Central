"use strict";

const CACHE_NAME = "central-shell-v1";
const IMAGE_CACHE_NAME = "central-images-v1";
const MAX_CACHED_IMAGES = 80;
const SHELL_URLS = [
  "/index.html",
  "/tienda.html",
  "/tarjetas.html",
  "/catalogo.html",
  "/producto.html",
  "/central.css",
  "/shopr.css",
  "/shopr-core.js",
  "/central-icon.svg",
  "/admin-manifest.json",
];
const SHELL_PATHS = new Set(SHELL_URLS);
const PAGE_FALLBACKS = new Map([
  ["/", "/index.html"],
  ["/index.html", "/index.html"],
  ["/central", "/index.html"],
  ["/admin", "/tarjetas.html"],
  ["/tarjetas", "/tarjetas.html"],
  ["/tarjetas.html", "/tarjetas.html"],
  ["/tienda", "/tienda.html"],
  ["/tienda.html", "/tienda.html"],
  ["/vitrina", "/tienda.html"],
  ["/catalogo", "/catalogo.html"],
  ["/catalogo.html", "/catalogo.html"],
  ["/producto.html", "/producto.html"],
]);

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(SHELL_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(key => (
          (key.startsWith("central-shell-") && key !== CACHE_NAME)
          || (key.startsWith("central-images-") && key !== IMAGE_CACHE_NAME)
        ))
          .map(key => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname === "/api/v1/media/image") {
    event.respondWith((async () => {
      const cache = await caches.open(IMAGE_CACHE_NAME);
      const cached = await cache.match(request);
      try {
        const response = await fetch(request);
        const contentType = response.headers.get("content-type") || "";
        const contentLength = Number(response.headers.get("content-length") || 0);
        if (response.ok && contentType.startsWith("image/") && contentLength > 0 && contentLength <= 5_000_000) {
          try {
            await cache.put(request, response.clone());
            const keys = await cache.keys();
            await Promise.all(keys.slice(0, Math.max(0, keys.length - MAX_CACHED_IMAGES)).map(key => cache.delete(key)));
          } catch (cacheError) {
            console.warn("No se pudo guardar una imagen para uso offline:", cacheError);
          }
        }
        return response;
      } catch (error) {
        if (cached) return cached;
        throw error;
      }
    })());
    return;
  }
  if (url.pathname === "/api" || url.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith((async () => {
      const fallbackPath = url.pathname.startsWith("/producto/")
        ? "/producto.html"
        : PAGE_FALLBACKS.get(url.pathname) || "/index.html";
      const cache = await caches.open(CACHE_NAME);
      try {
        const response = await fetch(request);
        if (response.ok) {
          await cache.put(new URL(fallbackPath, self.location.origin).href, response.clone());
        }
        return response;
      } catch {
        return await cache.match(new URL(fallbackPath, self.location.origin).href)
          || Response.error();
      }
    })());
    return;
  }

  if (!SHELL_PATHS.has(url.pathname)) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(request);
    const refresh = fetch(request).then(response => {
      if (response.ok) return cache.put(request, response.clone()).then(() => response);
      return response;
    });
    if (cached) {
      event.waitUntil(refresh.catch(error => {
        console.warn("No se pudo actualizar un recurso offline:", error);
      }));
      return cached;
    }
    return refresh;
  })());
});
