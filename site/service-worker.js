const CACHE='tw539-mobile-ironlaw-v6';
const APP_SHELL=['./','./index.html','./backtest.html','./review.html','./history.html','./models.html','./health.html','./manifest.webmanifest','./mobile-sync.js','./icons/icon-180.png','./icons/icon-192.png','./icons/icon-512.png','./icons/maskable-512.png'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(APP_SHELL)).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{
  if(e.request.method!=='GET')return;
  const url=new URL(e.request.url);
  if(url.origin!==self.location.origin)return;
  if(url.pathname.endsWith('version.json')||url.pathname.endsWith('latest-result.json')||url.pathname.endsWith('system-health.json')||url.pathname.endsWith('published-settlements.jsonl')){e.respondWith(fetch(e.request,{cache:'no-store'}));return;}
  // HTML一律網路優先且禁止舊快取冒充最新；只有離線時才使用快取。
  e.respondWith(fetch(e.request,{cache:'no-store'}).then(r=>{if(r.ok){const x=r.clone();caches.open(CACHE).then(c=>c.put(e.request,x))}return r}).catch(async()=>await caches.match(e.request)||await caches.match('./index.html')));
});
