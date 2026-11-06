const CACHE='fiscycle-shell-v3';
const SHELL=['/','/ecosystem','/bsf-intelligence','/manifest.webmanifest','/fiscycle-icon.svg','/assets/gateway.js','/assets/integration.js','/assets/integration.css','/assets/gallery.js','/assets/gallery.css'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL))));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key))))));
self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET'||new URL(event.request.url).pathname.startsWith('/api/')||new URL(event.request.url).pathname.startsWith('/water-quality/')) return;
  event.respondWith(fetch(event.request).then(response=>{if(response.ok&&SHELL.includes(new URL(event.request.url).pathname)){const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(event.request,copy));}return response;}).catch(()=>caches.match(event.request)));
});
