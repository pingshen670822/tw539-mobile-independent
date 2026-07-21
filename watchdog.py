#!/usr/bin/env python3
"""比較官方最新期別與公開手機頁；手機頁落後即失敗。"""
import html, json, re, time, urllib.request
from cloud_pipeline import fetch_latest

PAGE='https://pingshen670822.github.io/tw539-mobile-independent/system-health.json'
REPORT='https://pingshen670822.github.io/tw539-mobile-independent/'
RESULT='https://pingshen670822.github.io/tw539-mobile-independent/latest-result.json'
VERSION='https://pingshen670822.github.io/tw539-mobile-independent/version.json'
official=fetch_latest()
stamp=str(int(time.time()))
headers={'User-Agent':'TW539-ironlaw-watchdog/1.0','Cache-Control':'no-cache'}
req=urllib.request.Request(PAGE+'?t='+stamp,headers=headers)
with urllib.request.urlopen(req,timeout=40) as r: health=json.load(r)
report_req=urllib.request.Request(REPORT+'?t='+stamp,headers=headers)
with urllib.request.urlopen(report_req,timeout=40) as r: page=r.read().decode('utf-8')
result_req=urllib.request.Request(RESULT+'?t='+stamp,headers=headers)
with urllib.request.urlopen(result_req,timeout=40) as r: result=json.load(r)
version_req=urllib.request.Request(VERSION+'?t='+stamp,headers=headers)
with urllib.request.urlopen(version_req,timeout=40) as r: version=json.load(r)
errors=[]
if str(health.get('latest_period'))!=str(official['period']): errors.append(f"公開期別 {health.get('latest_period')} != 官方 {official['period']}")
if health.get('latest_draw_date')!=official['draw_date']: errors.append(f"公開日期 {health.get('latest_draw_date')} != 官方 {official['draw_date']}")
if not health.get('freshness_ok'): errors.append('公開頁新鮮度未通過')
if not health.get('full_history_mode'): errors.append('公開頁不是100%全歷史模式')
if not health.get('history_database_sha256'): errors.append('公開頁缺資料庫指紋')
data_latest=result.get('data_latest') or {}
if str(data_latest.get('period'))!=str(official['period']) or data_latest.get('date')!=official['draw_date']: errors.append('公開結果未對應官方最新期別')
ranked=result.get('ranked_top15') or []
if not ranked or result.get('single_candidate')!=ranked[0] or result.get('single_published')!=ranked[0]: errors.append('公開結果的1中1主選缺失')
coverage=result.get('history_coverage') or {}
if coverage.get('mode')!='all_available_history_for_every_prediction' or coverage.get('global_history_blend')!=1.0: errors.append('公開結果不是100%全歷史正式排名')
if coverage.get('database_sha256')!=health.get('history_database_sha256'): errors.append('公開結果與健康檔的資料庫指紋不同')
if str(version.get('latest_period'))!=str(official['period']) or version.get('latest_draw_date')!=official['draw_date']: errors.append('手機版本檔未同步官方最新期別')
visible=re.sub(r'(?is)<(?:style|script)\b[^>]*>.*?</(?:style|script)>',' ',page)
visible=html.unescape(re.sub(r'(?s)<[^>]+>',' ',visible))
english=sorted(set(re.findall(r'[A-Za-z][A-Za-z0-9_-]*',visible)))
if english: errors.append('戰報可見文字含英文：'+','.join(english))
if '1中1主選' not in visible or (ranked and f'{int(ranked[0]):02}' not in visible): errors.append('公開戰報未顯示1中1主選')
if errors: raise SystemExit('鐵律看門狗失敗：'+'；'.join(errors))
print(json.dumps({'看門狗':'通過','官方期別':official['period'],'公開期別':health['latest_period'],'全歷史':True,'1中1主選':result['single_published'],'戰報可見英文':0},ensure_ascii=False))
