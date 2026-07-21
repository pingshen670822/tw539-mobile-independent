#!/usr/bin/env python3
"""比較官方最新期別與公開手機頁；手機頁落後即失敗。"""
import json, time, urllib.request
from cloud_pipeline import fetch_latest

PAGE='https://pingshen670822.github.io/tw539-mobile-independent/system-health.json'
official=fetch_latest()
req=urllib.request.Request(PAGE+'?t='+str(int(time.time())),headers={'User-Agent':'TW539-ironlaw-watchdog/1.0','Cache-Control':'no-cache'})
with urllib.request.urlopen(req,timeout=40) as r: health=json.load(r)
errors=[]
if str(health.get('latest_period'))!=str(official['period']): errors.append(f"公開期別 {health.get('latest_period')} != 官方 {official['period']}")
if health.get('latest_draw_date')!=official['draw_date']: errors.append(f"公開日期 {health.get('latest_draw_date')} != 官方 {official['draw_date']}")
if not health.get('freshness_ok'): errors.append('公開頁新鮮度未通過')
if not health.get('full_history_mode'): errors.append('公開頁不是100%全歷史模式')
if not health.get('history_database_sha256'): errors.append('公開頁缺資料庫指紋')
if errors: raise SystemExit('鐵律看門狗失敗：'+'；'.join(errors))
print(json.dumps({'watchdog':'passed','official_period':official['period'],'published_period':health['latest_period'],'full_history':True},ensure_ascii=False))
