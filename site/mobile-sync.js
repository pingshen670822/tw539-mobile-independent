if('serviceWorker' in navigator) navigator.serviceWorker.register('./service-worker.js');
let current='';
async function checkVersion(){
  try{const r=await fetch('./version.json?t='+Date.now(),{cache:'no-store'});const v=await r.json();if(current&&current!==v.version) location.reload();current=v.version;}
  catch(e){}
}
checkVersion();setInterval(checkVersion,30000);
