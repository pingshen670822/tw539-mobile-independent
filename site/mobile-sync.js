if('serviceWorker' in navigator) navigator.serviceWorker.register('./service-worker.js');
let current='';
const syncState=document.createElement('div');
syncState.setAttribute('style','position:fixed;right:8px;bottom:8px;z-index:9999;padding:7px 10px;border-radius:9px;background:#172033;color:#fff;font:700 12px sans-serif;box-shadow:0 2px 8px #0005');
syncState.textContent='同步檢查中';
document.body.appendChild(syncState);
async function checkVersion(){
  try{const r=await fetch('./version.json?t='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error('同步失敗');const v=await r.json();if(current&&current!==v.version) location.reload();current=v.version;syncState.textContent='同步正常';syncState.style.background='#176b3a';}
  catch(e){syncState.textContent='網路中斷，顯示最近資料';syncState.style.background='#8b0000';}
}
checkVersion();setInterval(checkVersion,30000);
