{% load static %}// SIGMA — service worker. Solo estáticos y pantalla «sin conexión»; las páginas con datos nunca se guardan.
const VERSION = "sigma-v2";
const ESTATICOS = ["{% static 'nucleo/sigma.css' %}", "{% static 'nucleo/sigma.js' %}", "{% static 'nucleo/img/logo-garzas.svg' %}"];
const SIN_CONEXION = `<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#f3f2ea" media="(prefers-color-scheme: light)"><meta name="theme-color" content="#17211b" media="(prefers-color-scheme: dark)"><title>Sin conexión · SIGMA</title>
<style>
:root { color-scheme: light dark; --fondo: #f3f2ea; --panel: #fff; --texto: #1b2a20; --tenue: #5e6a62; --borde: #e2e0d3; --boton: #2f6b3a; }
@media (prefers-color-scheme: dark) { :root { --fondo: #101813; --panel: #17211b; --texto: #e8eee9; --tenue: #a8b5ac; --borde: #2b3a30; --boton: #3b8049; } }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; min-height: 100dvh; display: grid; place-items: center; padding: max(20px, env(safe-area-inset-top)) 20px max(20px, env(safe-area-inset-bottom)); background: var(--fondo); color: var(--texto); font: 1rem/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; text-align: center; }
main { width: min(100%, 26rem); padding: 28px 24px; background: var(--panel); border: 1px solid var(--borde); border-radius: 16px; }
img { display: block; width: 72px; height: 72px; margin: 0 auto 14px; }
h1 { margin: 0 0 6px; font-size: 1.4rem; line-height: 1.25; }
p { margin: 0 0 20px; color: var(--tenue); overflow-wrap: break-word; }
button { width: 100%; min-height: 48px; padding: 10px 18px; border: 0; border-radius: 8px; background: var(--boton); color: #fff; font: 600 1rem system-ui, sans-serif; cursor: pointer; }
button:focus-visible { outline: 3px solid #e2b33c; outline-offset: 2px; }
small { display: block; margin-top: 12px; color: var(--tenue); }
@media (max-height: 420px) { main { padding: 14px 20px; } img { width: 44px; height: 44px; margin-bottom: 6px; } p { margin-bottom: 10px; } small { display: none; } }
</style>
<main><img src="{% static 'nucleo/img/logo-garzas.svg' %}" alt="Frutera Las Garzas"><h1>Sin conexión</h1>
<p>No pudimos cargar SIGMA. Revisa tu internet: tus datos están guardados y no se perdió nada.</p>
<button type="button" onclick="location.reload()">Reintentar</button>
<small>Esta pantalla se actualiza sola cuando vuelve la conexión.</small></main>
<script>addEventListener("online", () => location.reload());</script></html>`;

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(ESTATICOS)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const r = e.request;
  if (r.method !== "GET") return;
  const u = new URL(r.url);
  if (u.origin !== location.origin) return;
  if (r.mode === "navigate") {
    e.respondWith(fetch(r).catch(() => new Response(SIN_CONEXION, { headers: { "Content-Type": "text/html; charset=utf-8" } })));
    return;
  }
  if (u.pathname.startsWith("/static/")) {
    e.respondWith(caches.open(VERSION).then((c) => c.match(r).then((hit) => {
      const red = fetch(r).then((res) => { if (res.ok) c.put(r, res.clone()); return res; }).catch(() => hit);
      return hit || red;
    })));
  }
});
