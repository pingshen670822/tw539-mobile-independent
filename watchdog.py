#!/usr/bin/env python3
"""比較官方最新期別與公開手機頁；手機頁落後即失敗。"""
import hashlib, html, json, re, time, urllib.request
from cloud_pipeline import fetch_latest

PAGE='https://pingshen670822.github.io/tw539-mobile-independent/system-health.json'
REPORT='https://pingshen670822.github.io/tw539-mobile-independent/'
RESULT='https://pingshen670822.github.io/tw539-mobile-independent/latest-result.json'
VERSION='https://pingshen670822.github.io/tw539-mobile-independent/version.json'
SETTLEMENTS='https://pingshen670822.github.io/tw539-mobile-independent/published-settlements.jsonl'
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
settlement_req=urllib.request.Request(SETTLEMENTS+'?t='+stamp,headers=headers)
with urllib.request.urlopen(settlement_req,timeout=40) as r: settlements=[json.loads(line) for line in r.read().decode('utf-8').splitlines() if line.strip()]
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
ranked_all=result.get('ranked_all') or []
if len(ranked_all)!=39 or set(ranked_all)!=set(range(1,40)) or ranked!=ranked_all[:15]: errors.append('公開結果缺少開獎前完整39碼排序')
if len(result.get('number_diagnostics') or [])!=39 or result.get('single_selection_evidence')!=(result.get('number_diagnostics') or [{}])[0]: errors.append('公開結果缺少最強獨隻逐模組證據')
seal=result.get('pre_draw_seal') or {}; sealed_payload=seal.get('sealed_payload') or {}
seal_hash=hashlib.sha256(json.dumps(sealed_payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
if seal.get('sha256')!=seal_hash or not seal.get('no_post_draw_substitution') or result.get('recalculation_fingerprint')!=seal_hash[:16]: errors.append('開獎前封存雜湊驗證失敗')
selection=(result.get('weight_selection_diagnostics') or [{}])[0]
if selection.get('candidate_count')!=286 or selection.get('method')!='rolling_all_history_286_grid_recent_three_fold_plus_long_history' or (selection.get('long_history_selection_window') or {}).get('samples',0)<1000: errors.append('開獎後沒有重新搜尋全部286組或缺少長歷史複驗')
overlap=result.get('previous_draw_overlap_audit') or {}
if overlap.get('method')!='model_score_with_repeat_qualification' or overlap.get('full_previous_draw_copied_into_top9') or set(data_latest.get('nums') or []).issubset(ranked[:9]): errors.append('公開結果仍整批複製上一期號碼或缺少連莊資格')
repeat_by_number={x.get('number'):x for x in (result.get('repeat_qualification') or [])}
for n in set(ranked[:9])&set(data_latest.get('nums') or []):
    if not (repeat_by_number.get(n) or {}).get('qualified'): errors.append(f'上一期號碼{int(n):02}未通過連莊資格卻列入前9')
    if not (repeat_by_number.get(n) or {}).get('repeat_backtest_pass'): errors.append(f'上一期號碼{int(n):02}個別連莊回測未達標卻列入前9')
excluded=set(result.get('forced_ticket_exclusions') or [])
if len(excluded)!=15 or any(set(ticket)&excluded for ticket in (result.get('tickets') or [])): errors.append('公開推薦牌組含強制投注排除號碼')
coverage=result.get('history_coverage') or {}
if coverage.get('mode')!='all_available_history_for_every_prediction' or coverage.get('global_history_blend')!=1.0: errors.append('公開結果不是100%全歷史正式排名')
if coverage.get('database_sha256')!=health.get('history_database_sha256'): errors.append('公開結果與健康檔的資料庫指紋不同')
backtest=result.get('backtest') or {}
if 'ranking_direction_valid' not in backtest or 'bottom1_hits' not in backtest or 'bottom5_avg_hits' not in backtest or 'bottom9_avg_hits' not in backtest: errors.append('公開結果缺少高低分方向驗證')
if bool(backtest.get('ranking_direction_valid'))!=bool(health.get('ranking_direction_valid')): errors.append('公開結果與健康檔的排序方向不同步')
if backtest.get('backtest_weights')!=result.get('production_weights') or result.get('audit_weights')!=result.get('production_weights'): errors.append('公開主選與隔離回測權重不同')
rolling=result.get('rolling_weight_adjustment') or {}
if rolling.get('production_weights')!=result.get('production_weights') or rolling.get('anchor_weights')!=selection.get('weights') or rolling.get('updates')!=360 or rolling.get('method')!='pre_draw_prediction_then_post_draw_module_error_update': errors.append('最新開獎錯誤沒有逐期回灌到下一期正式權重')
rate_selection=rolling.get('learning_rate_selection') or {}
if rate_selection.get('candidate_count')!=6 or not rate_selection.get('holdout_not_used') or rate_selection.get('selected_learning_rate')!=rolling.get('learning_rate'): errors.append('滾動學習幅度未以隔離期以前資料選定')
if backtest.get('anchor_weights')!=rolling.get('anchor_weights') or backtest.get('end_weights')!=result.get('production_weights') or backtest.get('rolling_update_count')!=360: errors.append('隔離回測沒有重演同一套逐期權重更新')
if backtest.get('rolling_learning_rate')!=rolling.get('learning_rate'): errors.append('隔離回測與正式滾動學習幅度不同')
full_scan=result.get('full_history_scan') or {}
if full_scan.get('samples')!=result.get('draw_count',0)-320 or not full_scan.get('ranking_direction_valid'): errors.append('公開結果的全歷史逐期掃描未通過')
if str(version.get('latest_period'))!=str(official['period']) or version.get('latest_draw_date')!=official['draw_date']: errors.append('手機版本檔未同步官方最新期別')
if not settlements:
    errors.append('公開頁缺少每期命中檢討結算檔')
else:
    review=settlements[-1]
    if review.get('target_draw_date')!=official['draw_date'] or str(review.get('official_period'))!=str(official['period']): errors.append('最新命中檢討未對應官方最新期別')
    if review.get('review_status')!='completed_from_pre_draw_seal' or len(review.get('actual_rankings') or [])!=5 or len(review.get('module_review') or [])!=len(result.get('production_weights') or {}): errors.append('最新命中檢討缺少實際排名或錯誤模組分析')
    if not (review.get('data_integrity') or {}).get('no_post_draw_substitution'): errors.append('命中檢討未禁止開獎後換號')
    if not (review.get('rolling_adjustment') or {}).get('completed') or (review.get('rolling_adjustment') or {}).get('candidate_count')!=286: errors.append('命中檢討後沒有完成286組滾動重算')
    if not health.get('settled_previous'): errors.append('健康檔沒有標示最新命中檢討完成')
visible=re.sub(r'(?is)<(?:style|script)\b[^>]*>.*?</(?:style|script)>',' ',page)
visible=html.unescape(re.sub(r'(?s)<[^>]+>',' ',visible))
english=sorted(set(re.findall(r'[A-Za-z][A-Za-z0-9_-]*',visible)))
if english: errors.append('戰報可見文字含英文：'+','.join(english))
if '1中1主選' not in visible or (ranked and f'{int(ranked[0]):02}' not in visible): errors.append('公開戰報未顯示1中1主選')
if '低機率' in visible or '當期預測前九' in visible: errors.append('公開戰報仍含易誤解標示或事後回算內容')
if '每期開獎命中檢討與滾動修正' not in visible or '錯誤模組逐項檢討' not in visible or '開獎後滾動權重重算' not in visible or '禁止開獎後換號或補號' not in visible: errors.append('公開戰報缺少每期命中檢討或滾動修正')
if '強制投注排除名單' not in visible or '全歷史逐期一致性掃描' not in visible or '上一期號碼檢查' not in visible or '連莊資格驗算' not in visible or '全歷史連莊率不低於12.82%' not in visible: errors.append('公開戰報缺少投注排除、全歷史掃描或連莊資格')
expected_direction='排序方向通過' if backtest.get('ranking_direction_valid') else '排序方向未通過'
if expected_direction not in visible: errors.append('公開戰報未照實顯示排序方向')
if errors: raise SystemExit('鐵律看門狗失敗：'+'；'.join(errors))
print(json.dumps({'看門狗':'通過','官方期別':official['period'],'公開期別':health['latest_period'],'全歷史':True,'命中檢討':'完成','滾動候選':286,'1中1主選':result['single_published'],'戰報可見英文':0},ensure_ascii=False))
