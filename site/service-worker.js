const CACHE='tw539-mobile-ironlaw-v3';
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(['./','./index.html','./manifest.webmanifest'])).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{
  if(e.request.url.includes('version.json')||e.request.url.includes('latest-result.json')||e.request.url.includes('system-health.json')){e.respondWith(fetch(e.request,{cache:'no-store'}));return;}
  // HTML一律網路優先且禁止舊快取冒充最新；只有離線時才使用快取。
  e.respondWith(fetch(e.request,{cache:'no-store'}).then(r=>{const x=r.clone();caches.open(CACHE).then(c=>c.put(e.request,x));return r}).catch(()=>caches.match(e.request)));
});
