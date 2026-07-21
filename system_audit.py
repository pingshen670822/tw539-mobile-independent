#!/usr/bin/env python3
"""台灣539整套系統離線全面驗收；任何鐵律不符均回傳失敗。"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from cloud_pipeline import expected_latest_date
from tw539_ultra import GLOBAL_HISTORY_BLEND, GLOBAL_HISTORY_WEIGHTS, load_draws, valid_ticket

ROOT=Path(__file__).resolve().parent
CSV=ROOT/'data'/'539.csv'
REPORTS=ROOT/'reports'
SITE=ROOT/'site'
errors=[]

def fail(message):
    errors.append(message)

def read_json(path):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        fail(f'{path.name} 無法讀取：{exc}')
        return {}

def visible_text(path):
    try: page=path.read_text(encoding='utf-8')
    except Exception as exc:
        fail(f'{path.name} 無法讀取：{exc}')
        return ''
    page=re.sub(r'(?is)<(?:style|script)\b[^>]*>.*?</(?:style|script)>',' ',page)
    return html.unescape(re.sub(r'(?s)<[^>]+>',' ',page))

draws=load_draws(CSV)
with CSV.open('r',encoding='utf-8-sig',newline='') as stream:
    raw=list(csv.DictReader(stream))
if len(raw)!=len(draws): fail('歷史資料含無效列、重複期別或遭靜默略過')
if len(draws)<5000: fail('全歷史資料期數異常不足')
if len({x['period'] for x in draws})!=len(draws): fail('歷史資料期別重複')
if len({x['date'] for x in draws})!=len(draws): fail('歷史資料日期重複')
if [(x['date'],x['period']) for x in draws]!=sorted((x['date'],x['period']) for x in draws): fail('歷史資料未依日期期別排序')
for draw in draws:
    try: datetime.strptime(draw['date'],'%Y-%m-%d')
    except ValueError: fail(f"歷史日期格式錯誤：{draw['date']}")
    if len(draw['nums'])!=5 or len(set(draw['nums']))!=5 or min(draw['nums'])<1 or max(draw['nums'])>39:
        fail(f"歷史號碼錯誤：{draw['period']}")

result=read_json(REPORTS/'最新結果.json')
site_result=read_json(SITE/'latest-result.json')
health=read_json(REPORTS/'system-health.json')
site_health=read_json(SITE/'system-health.json')
version=read_json(SITE/'version.json')
latest=draws[-1]

if result.get('data_latest',{}).get('period')!=latest['period'] or result.get('data_latest',{}).get('date')!=latest['date']:
    fail('最新結果未對應歷史資料庫末期')
if result.get('draw_count')!=len(draws): fail('最新結果的全歷史期數不符')
coverage=result.get('history_coverage') or {}
if coverage.get('mode')!='all_available_history_for_every_prediction': fail('正式預測不是全歷史模式')
if coverage.get('draws_used')!=len(draws) or coverage.get('numbers_used')!=len(draws)*5: fail('全歷史使用量不符')
if coverage.get('global_history_blend')!=GLOBAL_HISTORY_BLEND or GLOBAL_HISTORY_BLEND!=1.0: fail('全歷史正式權重不是百分之百')
weights=result.get('production_weights') or {}
if set(weights)!=set(GLOBAL_HISTORY_WEIGHTS): fail('正式模型混入非全歷史特徵或缺少全歷史特徵')
if abs(sum(float(x) for x in weights.values())-1)>1e-9: fail('正式模型權重總和不是一')

history_payload='|'.join(f"{x['period']}:{x['date']}:{','.join(map(str,x['nums']))}" for x in draws)
database_hash=hashlib.sha256(history_payload.encode()).hexdigest()
if coverage.get('database_sha256')!=database_hash: fail('最新結果的歷史資料庫指紋不符')
if health.get('history_database_sha256')!=database_hash or site_health.get('history_database_sha256')!=database_hash: fail('健康檔的歷史資料庫指紋不符')

ranked=result.get('ranked_top15') or []
if len(ranked)!=15 or len(set(ranked))!=15 or any(not 1<=int(n)<=39 for n in ranked): fail('前十五名資料錯誤')
elif result.get('single_candidate')!=ranked[0] or result.get('single_published')!=ranked[0]: fail('1中1主選未固定產出並公開')
if not (result.get('release_policy') or {}).get('official_release_allowed'): fail('主選公開狀態遭門檻封鎖')

target=datetime.strptime(latest['date'],'%Y-%m-%d').date()+timedelta(days=1)
while target.weekday()==6: target+=timedelta(days=1)
if result.get('target_draw_date')!=target.isoformat(): fail('預測目標日期錯誤')
fingerprint_payload=json.dumps({'based_on':latest['period'],'weights':weights,'top15':ranked},sort_keys=True)
if result.get('recalculation_fingerprint')!=hashlib.sha256(fingerprint_payload.encode()).hexdigest()[:16]: fail('預測重算指紋錯誤')

tickets=[tuple(int(n) for n in ticket) for ticket in (result.get('tickets') or [])]
if not tickets or len(tickets)!=len(set(tickets)): fail('精選組合缺失或重複')
for ticket in tickets:
    if len(ticket)!=5 or len(set(ticket))!=5 or not valid_ticket(tuple(sorted(ticket))): fail('精選組合未通過牌型限制')
for index,ticket in enumerate(tickets):
    if any(len(set(ticket)&set(other))>3 for other in tickets[:index]): fail('精選組合彼此重疊過高')
backtest=result.get('backtest') or {}
if backtest.get('samples')!=360: fail('隔離回測不是三百六十期')
if sum(int(v) for v in (backtest.get('distribution') or {}).values())!=backtest.get('samples'): fail('隔離回測分布加總錯誤')
for key in ('single_rate','single_random_baseline','single_wilson_lower95'):
    if not 0<=float(backtest.get(key,-1))<=1: fail(f'隔離回測數值錯誤：{key}')

if site_result!=result: fail('手機結果與戰報結果不同步')
if site_health!=health: fail('手機健康檔與戰報健康檔不同步')
for label,item in (('戰報健康檔',health),('手機健康檔',site_health)):
    if item.get('latest_period')!=latest['period'] or item.get('latest_draw_date')!=latest['date']: fail(f'{label}期別日期錯誤')
    if not item.get('full_history_mode'): fail(f'{label}不是全歷史模式')
    if not item.get('model_release_allowed') or not item.get('single_release_allowed'): fail(f'{label}仍會封鎖主選公開')
    if not item.get('freshness_ok') or latest['date']<expected_latest_date(): fail(f'{label}資料新鮮度錯誤')
if version.get('latest_period')!=latest['period'] or version.get('latest_draw_date')!=latest['date']: fail('手機版本檔期別日期錯誤')

for path in (REPORTS/'最新539科學預測戰報.html',SITE/'index.html'):
    visible=visible_text(path)
    english=sorted(set(re.findall(r'[A-Za-z][A-Za-z0-9_-]*',visible)))
    if english: fail(f'{path.name} 可見文字含英文：'+','.join(english))
    for term in ('1中1主選','公開狀態','已公開','全歷史核心占比','每期固定產出並公開'):
        if term not in visible: fail(f'{path.name} 缺少：{term}')
    if ranked and f'{int(ranked[0]):02}' not in visible: fail(f'{path.name} 未顯示當期1中1主選')

service=(SITE/'service-worker.js').read_text(encoding='utf-8')
sync=(SITE/'mobile-sync.js').read_text(encoding='utf-8')
if "cache:'no-store'" not in service or 'system-health.json' not in service: fail('手機快取可能保留過期資料')
if 'setInterval(checkVersion,30000)' not in sync: fail('手機每三十秒同步檢查已損壞')

history_file=REPORTS/'prediction-history.jsonl'
try:
    records=[json.loads(line) for line in history_file.read_text(encoding='utf-8').splitlines() if line.strip()]
    match=[x for x in records if x.get('recalculation_fingerprint')==result.get('recalculation_fingerprint')]
    if not match or match[-1].get('single_published')!=result.get('single_published'): fail('預測歷史未保存當期公開主選')
except Exception as exc: fail(f'預測歷史無法驗證：{exc}')

settlements=REPORTS/'published-settlements.jsonl'
if settlements.exists():
    try:
        for line in settlements.read_text(encoding='utf-8').splitlines():
            if not line.strip(): continue
            item=json.loads(line)
            if item.get('single_published') is None or item.get('single_hit') not in (True,False): fail('已結算紀錄缺少1中1公開主選或命中結果')
    except Exception as exc: fail(f'已結算紀錄無法驗證：{exc}')

if errors:
    raise SystemExit('整套系統驗收失敗：'+'；'.join(dict.fromkeys(errors)))
print(json.dumps({'全面驗收':'通過','歷史期數':len(draws),'最新期別':latest['period'],'全歷史占比':'100%','1中1主選':result['single_published'],'戰報可見英文':0},ensure_ascii=False))
