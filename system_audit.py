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
from tw539_ultra import FORMAL_FEATURE_KEYS, GLOBAL_HISTORY_BLEND, MODEL_SEARCH_CANDIDATE_COUNT, MODEL_SELECTION_DATE, MODEL_SELECTION_PERIOD, MODEL_SELECTION_VALIDATION, load_draws, rank_numbers, ranking_direction_metrics, scores, valid_ticket

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
if not str(result.get('generated_at','')).endswith('+08:00'): fail('戰報產生時間不是台灣時區')
if not str(health.get('checked_at','')).endswith('+08:00') or not str(version.get('updated_at','')).endswith('+08:00'): fail('雲端健康或手機版本時間不是台灣時區')
equal_scores={n:0.0 for n in range(1,40)}
tie_order=rank_numbers(equal_scores,latest['period'])
if tie_order!=rank_numbers(equal_scores,latest['period']) or tie_order in (list(range(1,40)),list(range(39,0,-1))): fail('公平破同分規則不穩定或仍固定偏向號碼大小')

if result.get('data_latest',{}).get('period')!=latest['period'] or result.get('data_latest',{}).get('date')!=latest['date']:
    fail('最新結果未對應歷史資料庫末期')
if result.get('draw_count')!=len(draws): fail('最新結果的全歷史期數不符')
coverage=result.get('history_coverage') or {}
if coverage.get('mode')!='all_available_history_for_every_prediction': fail('正式預測不是全歷史模式')
if coverage.get('draws_used')!=len(draws) or coverage.get('numbers_used')!=len(draws)*5: fail('全歷史使用量不符')
if coverage.get('global_history_blend')!=GLOBAL_HISTORY_BLEND or GLOBAL_HISTORY_BLEND!=1.0: fail('全歷史正式權重不是百分之百')
weights=result.get('production_weights') or {}
if not weights or not set(weights).issubset(set(FORMAL_FEATURE_KEYS)): fail('正式模型混入非全歷史或未核准特徵')
if abs(sum(float(x) for x in weights.values())-1)>1e-9: fail('正式模型權重總和不是一')
if result.get('audit_weights')!=weights: fail('正式主選與隔離回測不是同一組權重')
cutoff=result.get('model_selection_cutoff') or {}
if cutoff.get('period')!=MODEL_SELECTION_PERIOD or cutoff.get('date')!=MODEL_SELECTION_DATE: fail('正式權重沒有鎖定在隔離保留期以前的校正截止點')
cutoff_index=next((i for i,x in enumerate(draws) if x['period']==MODEL_SELECTION_PERIOD and x['date']==MODEL_SELECTION_DATE),-1)
if cutoff_index<0 or len(draws)-cutoff_index-1<360: fail('模型校正截止點與最後三百六十期沒有完全隔離')
diagnostics=result.get('weight_selection_diagnostics') or []
if len(diagnostics)!=1 or sum(bool(x.get('selected')) for x in diagnostics)!=1: fail('多區段穩定性選模紀錄不完整')
else:
    selected=diagnostics[0]
    validation=selected.get('validation') or {}
    if selected.get('candidate_count')!=MODEL_SEARCH_CANDIDATE_COUNT or MODEL_SEARCH_CANDIDATE_COUNT<1000: fail('多模組候選組合搜尋數量不足')
    if selected.get('weights')!=weights: fail('校正選定權重與正式權重不同')
    if validation.get('samples')!=360 or not validation.get('ranking_direction_valid') or not validation.get('folds_all_valid'): fail('前段三折校正沒有全數通過')
validation_start=next((i for i,x in enumerate(draws) if x['period']==MODEL_SELECTION_VALIDATION['first_period']),-1)
if validation_start<0 or cutoff_index-validation_start+1!=360:
    fail('前段三百六十期校正區段不完整')
else:
    recalculated_validation=ranking_direction_metrics(draws,weights,validation_start,cutoff_index+1)
    for key in ('samples','single_hits','bottom1_hits','top5_avg_hits','bottom5_avg_hits','top9_avg_hits','bottom9_avg_hits','avg_actual_rank','ranking_direction_valid'):
        if recalculated_validation.get(key)!=MODEL_SELECTION_VALIDATION.get(key): fail(f'前段校正獨立重算不符：{key}')
    for fold in range(3):
        a=validation_start+fold*120; b=a+120
        if not ranking_direction_metrics(draws,weights,a,b).get('ranking_direction_valid'): fail(f'前段第{fold+1}折排序方向未通過')

history_payload='|'.join(f"{x['period']}:{x['date']}:{','.join(map(str,x['nums']))}" for x in draws)
database_hash=hashlib.sha256(history_payload.encode()).hexdigest()
if coverage.get('database_sha256')!=database_hash: fail('最新結果的歷史資料庫指紋不符')
if health.get('history_database_sha256')!=database_hash or site_health.get('history_database_sha256')!=database_hash: fail('健康檔的歷史資料庫指紋不符')

ranked=result.get('ranked_top15') or []
if len(ranked)!=15 or len(set(ranked))!=15 or any(not 1<=int(n)<=39 for n in ranked): fail('前十五名資料錯誤')
elif result.get('single_candidate')!=ranked[0] or result.get('single_published')!=ranked[0]: fail('1中1主選未固定產出並公開')
if ranked!=rank_numbers(scores(draws,weights),latest['period'])[:15]: fail('正式排名未使用公平破同分規則或結果不可重現')
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
for key in ('bottom1_hits','bottom5_avg_hits','bottom9_avg_hits','avg_actual_rank','ranking_direction_valid','backtest_weights'):
    if key not in backtest: fail(f'隔離回測缺少高低分方向欄位：{key}')
calculated_direction=(backtest.get('single_hits',0)>backtest.get('bottom1_hits',0) and backtest.get('top5_avg_hits',0)>backtest.get('bottom5_avg_hits',0) and backtest.get('top9_avg_hits',0)>backtest.get('bottom9_avg_hits',0) and backtest.get('avg_actual_rank',99)<20)
if bool(backtest.get('ranking_direction_valid'))!=calculated_direction: fail('高低分方向判定與實際數據不符')
if not calculated_direction: fail('校正後正式模型的最後三百六十期排序方向未通過')
if backtest.get('backtest_weights')!=weights: fail('隔離回測權重與正式主選權重不同')
recalculated_holdout=ranking_direction_metrics(draws,weights,len(draws)-360,len(draws))
for key in ('samples','single_hits','bottom1_hits','top5_avg_hits','bottom5_avg_hits','top9_avg_hits','bottom9_avg_hits','avg_actual_rank','ranking_direction_valid'):
    if recalculated_holdout.get(key)!=backtest.get(key): fail(f'最後三百六十期獨立重算不符：{key}')

if site_result!=result: fail('手機結果與戰報結果不同步')
if site_health!=health: fail('手機健康檔與戰報健康檔不同步')
for label,item in (('戰報健康檔',health),('手機健康檔',site_health)):
    if item.get('latest_period')!=latest['period'] or item.get('latest_draw_date')!=latest['date']: fail(f'{label}期別日期錯誤')
    if not item.get('full_history_mode'): fail(f'{label}不是全歷史模式')
    if not item.get('model_release_allowed') or not item.get('single_release_allowed'): fail(f'{label}仍會封鎖主選公開')
    if not item.get('freshness_ok') or latest['date']<expected_latest_date(): fail(f'{label}資料新鮮度錯誤')
    if bool(item.get('ranking_direction_valid'))!=bool(backtest.get('ranking_direction_valid')): fail(f'{label}未同步排序方向狀態')
if version.get('latest_period')!=latest['period'] or version.get('latest_draw_date')!=latest['date']: fail('手機版本檔期別日期錯誤')

for path in (REPORTS/'最新539科學預測戰報.html',SITE/'index.html'):
    visible=visible_text(path)
    english=sorted(set(re.findall(r'[A-Za-z][A-Za-z0-9_-]*',visible)))
    if english: fail(f'{path.name} 可見文字含英文：'+','.join(english))
    for term in ('1中1主選','公開狀態','已公開','全歷史核心占比','每期固定產出並公開','相對指數（非機率）','開獎前封存實戰紀錄','排序後段對照'):
        if term not in visible: fail(f'{path.name} 缺少：{term}')
    expected_direction='排序方向通過' if backtest.get('ranking_direction_valid') else '排序方向未通過'
    if expected_direction not in visible: fail(f'{path.name} 未照實顯示高低分方向')
    if '低機率精準暫避' in visible or '當期預測前九' in visible: fail(f'{path.name} 仍含事後回算或未驗證低機率標示')
    if ranked and f'{int(ranked[0]):02}' not in visible: fail(f'{path.name} 未顯示當期1中1主選')
    generated_visible=str(result.get('generated_at',''))[:16].replace('T',' ')
    if generated_visible and generated_visible not in visible: fail(f'{path.name} 戰報產生時間未同步台灣時區')

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
            if item.get('single_published') is None or item.get('single_hit') not in (True,False) or len(item.get('top5_published') or [])!=5: fail('已結算紀錄缺少開獎前封存主選或前5')
    except Exception as exc: fail(f'已結算紀錄無法驗證：{exc}')

if errors:
    raise SystemExit('整套系統驗收失敗：'+'；'.join(dict.fromkeys(errors)))
print(json.dumps({'全面驗收':'通過','歷史期數':len(draws),'最新期別':latest['period'],'全歷史占比':'100%','1中1主選':result['single_published'],'排序方向':'通過' if backtest.get('ranking_direction_valid') else '未通過','戰報可見英文':0},ensure_ascii=False))
