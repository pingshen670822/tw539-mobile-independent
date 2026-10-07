if('serviceWorker' in navigator) navigator.serviceWorker.register('./service-worker.js').then(r=>r.update()).catch(()=>{});
const installButton=document.getElementById('install-app-button');
const installStatus=document.getElementById('install-app-status');
const installHelp=document.getElementById('install-app-help');
const cloudControlStatus=document.getElementById('cloud-control-status');
const manualUpdateButton=document.getElementById('manual-update-button');
const repairButton=document.getElementById('emergency-repair-button');
if(repairButton)repairButton.addEventListener('click',()=>{
  if(cloudControlStatus)cloudControlStatus.textContent='已開啟受保護的當機修復控制頁';
});
async function manualCloudSync(){
  if(!manualUpdateButton||manualUpdateButton.disabled)return;
  manualUpdateButton.disabled=true;
  if(cloudControlStatus)cloudControlStatus.textContent='正在清除舊快取並重新取得雲端資料';
  try{
    if('caches' in window)await Promise.all((await caches.keys()).map(key=>caches.delete(key)));
    if('serviceWorker' in navigator){
      const registrations=await navigator.serviceWorker.getRegistrations();
      await Promise.all(registrations.map(registration=>registration.update()));
    }
    const stamp=Date.now();
    const [versionResponse,resultResponse,healthResponse]=await Promise.all([
      fetch('./version.json?manual='+stamp,{cache:'no-store',headers:{'Cache-Control':'no-cache'}}),
      fetch('./latest-result.json?manual='+stamp,{cache:'no-store',headers:{'Cache-Control':'no-cache'}}),
      fetch('./system-health.json?manual='+stamp,{cache:'no-store',headers:{'Cache-Control':'no-cache'}})
    ]);
    if(!versionResponse.ok||!resultResponse.ok||!healthResponse.ok)throw new Error('雲端資料取得失敗');
    const [version,result,health]=await Promise.all([versionResponse.json(),resultResponse.json(),healthResponse.json()]);
    if(!version.version||!result.target_draw_date||!health.latest_period)throw new Error('雲端資料不完整');
    if(cloudControlStatus)cloudControlStatus.textContent='雲端資料已取得，正在載入最新版本';
    sessionStorage.setItem('tw539-manual-sync',JSON.stringify({version:version.version,time:Date.now()}));
    await new Promise(resolve=>setTimeout(resolve,500));
    location.replace(location.pathname+'?v='+encodeURIComponent(version.version)+'&manual='+stamp+location.hash);
  }catch(error){
    if(cloudControlStatus)cloudControlStatus.textContent='更新失敗，五秒後自動重試；請檢查網路連線';
    manualUpdateButton.disabled=false;
    setTimeout(checkVersion,5000);
  }
}
if(manualUpdateButton)manualUpdateButton.addEventListener('click',manualCloudSync);
let installPrompt=null;
const installedMode=()=>matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;
function showInstallState(){
  if(!installButton||!installStatus)return;
  if(installedMode()){
    installButton.hidden=true;installHelp.hidden=true;installStatus.hidden=false;installStatus.textContent='手機版已安裝';
  }else{
    installButton.hidden=false;installStatus.hidden=true;
  }
}
addEventListener('beforeinstallprompt',event=>{
  event.preventDefault();installPrompt=event;showInstallState();
});
addEventListener('appinstalled',()=>{
  installPrompt=null;showInstallState();
});
if(installButton)installButton.addEventListener('click',async()=>{
  if(installPrompt){
    installPrompt.prompt();
    const choice=await installPrompt.userChoice;
    if(choice.outcome==='accepted'){
      installStatus.hidden=false;installStatus.textContent='正在安裝手機版';installButton.hidden=true;installHelp.hidden=true;
    }else{
      installHelp.hidden=false;installButton.setAttribute('aria-expanded','true');
    }
    installPrompt=null;
    return;
  }
  installHelp.hidden=!installHelp.hidden;
  installButton.setAttribute('aria-expanded',String(!installHelp.hidden));
});
showInstallState();
const pageVersion=(document.querySelector("meta[name='tw539-version']")||{}).content||'';
let current=pageVersion;
let timer=null;
let syncInFlight=false;
const SYNC_TIMEOUT_MS=10000;
const SUCCESS_SYNC_DELAY_MS=30000;
const RETRY_SYNC_DELAY_MS=5000;
const syncState=document.createElement('div');
syncState.setAttribute('style','position:fixed;right:8px;bottom:8px;z-index:9999;padding:7px 10px;border-radius:9px;background:#172033;color:#fff;font:700 12px sans-serif;box-shadow:0 2px 8px #0005');
syncState.textContent='同步檢查中';
document.body.appendChild(syncState);
async function checkVersion(){
  clearTimeout(timer);
  if(syncInFlight){timer=setTimeout(checkVersion,2000);return;}
  syncInFlight=true;
  const controller=new AbortController();
  const timeout=setTimeout(()=>controller.abort(),SYNC_TIMEOUT_MS);
  let nextDelay=RETRY_SYNC_DELAY_MS;
  try{
    const r=await fetch('./version.json?t='+Date.now(),{cache:'no-store',headers:{'Cache-Control':'no-cache'},signal:controller.signal});
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
    current=v.version;syncState.textContent='同步正常・'+v.latest_draw_date;syncState.style.background='#176b3a';nextDelay=SUCCESS_SYNC_DELAY_MS;
  }
  catch(e){syncState.textContent=e.name==='AbortError'?'同步逾時，立即重試':'同步重試中';syncState.style.background='#8b0000';}
  finally{
    clearTimeout(timeout);
    syncInFlight=false;
    timer=setTimeout(checkVersion,nextDelay);
  }
}
checkVersion();
addEventListener('focus',checkVersion);
addEventListener('online',checkVersion);
addEventListener('pageshow',checkVersion);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkVersion()});
