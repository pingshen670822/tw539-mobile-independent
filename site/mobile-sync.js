if('serviceWorker' in navigator) navigator.serviceWorker.register('./service-worker.js').then(r=>r.update());
const pageVersion=(document.querySelector("meta[name='tw539-version']")||{}).content||'';
let current=pageVersion;
let timer=null;
const syncState=document.createElement('div');
syncState.setAttribute('style','position:fixed;right:8px;bottom:8px;z-index:9999;padding:7px 10px;border-radius:9px;background:#172033;color:#fff;font:700 12px sans-serif;box-shadow:0 2px 8px #0005');
syncState.textContent='同步檢查中';
document.body.appendChild(syncState);
async function checkVersion(){
  clearTimeout(timer);
  try{
    const r=await fetch('./version.json?t='+Date.now(),{cache:'no-store',headers:{'Cache-Control':'no-cache'}});
    if(!r.ok)throw new Error('同步失敗');
    const v=await r.json();
    if(current&&current!==v.version){
      syncState.textContent='發現新資料，立即更新';syncState.style.background='#b8860b';
      const mark=JSON.parse(sessionStorage.getItem('tw539-reload')||'{"version":"","time":0}');
      if(mark.version!==v.version||Date.now()-mark.time>5000){
        sessionStorage.setItem('tw539-reload',JSON.stringify({version:v.version,time:Date.now()}));
        if('caches' in window)await Promise.all((await caches.keys()).map(key=>caches.delete(key)));
        location.replace(location.pathname+'?v='+encodeURIComponent(v.version)+location.hash);
        return;
      }
    }
    current=v.version;syncState.textContent='同步正常・'+v.latest_draw_date;syncState.style.background='#176b3a';
    timer=setTimeout(checkVersion,30000);
  }
  catch(e){syncState.textContent='同步重試中';syncState.style.background='#8b0000';timer=setTimeout(checkVersion,5000);}
}
checkVersion();
addEventListener('focus',checkVersion);
addEventListener('online',checkVersion);
addEventListener('pageshow',checkVersion);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkVersion()});
