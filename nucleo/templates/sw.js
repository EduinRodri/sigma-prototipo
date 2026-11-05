{% load static %}// SIGMA — service worker. Solo estáticos y pantalla «sin conexión»; las páginas con datos nunca se guardan.
const VERSION = "sigma-v1";
const ESTATICOS = ["{% static 'nucleo/sigma.css' %}", "{% static 'nucleo/sigma.js' %}", "{% static 'nucleo/img/logo-garzas.svg' %}"];
const SIN_CONEXION = `<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sin conexión · SIGMA</title>
<body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#f3f2ea;color:#1b2a20;font:16px system-ui,sans-serif;text-align:center;padding:24px">
<div><div style="width:64px;height:64px;margin:0 auto 12px;border-radius:50%;background:#2f6b3a"></div><h1 style="font-size:1.3rem;margin:0 0 6px">Sin conexión</h1>
<p style="color:#56635a;margin:0 0 18px">SIGMA necesita internet para mostrar anticipos y gastos reales.</p>
<button onclick="location.reload()" style="height:46px;padding:0 22px;border:0;border-radius:6px;background:#2f6b3a;color:#fff;font:600 1rem system-ui">Reintentar</button></div></body></html>`;

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
