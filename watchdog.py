#!/usr/bin/env python3
"""比較官方最新期別與公開手機頁；手機頁落後即失敗。"""
import hashlib, html, json, re, time, urllib.request
from datetime import datetime, time as clock_time
from cloud_pipeline import TAIPEI, expected_latest_date, fetch_latest

PAGE='https://pingshen670822.github.io/tw539-mobile-independent/system-health.json'
REPORT_ROOT='https://pingshen670822.github.io/tw539-mobile-independent/'
REPORT_PAGES=('index.html','backtest.html','review.html','history.html','models.html','health.html')
RESULT='https://pingshen670822.github.io/tw539-mobile-independent/latest-result.json'
VERSION='https://pingshen670822.github.io/tw539-mobile-independent/version.json'
SETTLEMENTS='https://pingshen670822.github.io/tw539-mobile-independent/published-settlements.jsonl'
official=fetch_latest()
stamp=str(int(time.time()))
headers={'User-Agent':'TW539-ironlaw-watchdog/1.0','Cache-Control':'no-cache'}
req=urllib.request.Request(PAGE+'?t='+stamp,headers=headers)
with urllib.request.urlopen(req,timeout=40) as r: health=json.load(r)
pages={}
for name in REPORT_PAGES:
    report_req=urllib.request.Request(REPORT_ROOT+name+'?t='+stamp,headers=headers)
    with urllib.request.urlopen(report_req,timeout=40) as r: pages[name]=r.read().decode('utf-8')
result_req=urllib.request.Request(RESULT+'?t='+stamp,headers=headers)
with urllib.request.urlopen(result_req,timeout=40) as r: result=json.load(r)
version_req=urllib.request.Request(VERSION+'?t='+stamp,headers=headers)
with urllib.request.urlopen(version_req,timeout=40) as r: version=json.load(r)
settlement_req=urllib.request.Request(SETTLEMENTS+'?t='+stamp,headers=headers)
with urllib.request.urlopen(settlement_req,timeout=40) as r: settlements=[json.loads(line) for line in r.read().decode('utf-8').splitlines() if line.strip()]
errors=[]
warnings=[]
now=datetime.now(TAIPEI)
deadline_active=now.time()>=clock_time(22,40) or now.time()<clock_time(6,0)
if deadline_active and official['draw_date']<expected_latest_date(now): errors.append('開獎後兩小時官方資料仍未取得，必須啟動自主修復')
if str(health.get('latest_period'))!=str(official['period']): errors.append(f"公開期別 {health.get('latest_period')} != 官方 {official['period']}")
if health.get('latest_draw_date')!=official['draw_date']: errors.append(f"公開日期 {health.get('latest_draw_date')} != 官方 {official['draw_date']}")
if not health.get('freshness_ok'): errors.append('公開頁新鮮度未通過')
if not health.get('full_history_mode'): errors.append('公開頁不是100%全歷史模式')
if not health.get('history_database_sha256'): errors.append('公開頁缺資料庫指紋')
for key in ('sync_completed_at','sync_delay_minutes','two_hour_repair_deadline','two_hour_deadline_met','self_repair_status','self_repair_count','last_public_verification_at','mobile_open_sync'):
    if key not in health: errors.append('公開健康檔缺少自主修復欄位：'+key)
if not health.get('two_hour_deadline_met',True): warnings.append('本期超過兩小時期限後才完成同步')
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
ensemble=result.get('production_ensemble_weights') or []
anchor_ensemble=result.get('anchor_ensemble_weights') or []
if selection.get('candidate_count')!=286 or selection.get('eligible_candidate_count')!=146 or selection.get('method')!='balanced_three_model_consensus_all_history_286_grid' or (selection.get('long_history_selection_window') or {}).get('samples',0)<1000: errors.append('開獎後沒有完成286組搜尋、146組均衡篩選或長歷史複驗')
if ensemble or len(anchor_ensemble)!=3 or len(selection.get('ensemble_members') or [])!=3: errors.append('公開結果仍錯用同質三模型，或缺少分散錨定模型')
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
if 'ranking_direction_valid' not in backtest or 'bottom1_hits' not in backtest or 'bottom5_avg_hits' not in backtest or 'bottom9_avg_hits' not in backtest or 'rank10_15_avg_hits' not in backtest or 'top9_capture_rate' not in backtest or 'boundary_control_valid' not in backtest: errors.append('公開結果缺少高低分與前9邊界驗證')
if bool(backtest.get('ranking_direction_valid'))!=bool(health.get('ranking_direction_valid')): errors.append('公開結果與健康檔的排序方向不同步')
if backtest.get('rank10_15_avg_hits')!=health.get('rank10_15_avg_hits') or backtest.get('top9_capture_rate')!=health.get('top9_capture_rate') or bool(backtest.get('boundary_control_valid'))!=bool(health.get('boundary_control_valid')): errors.append('公開結果與健康檔的前9邊界狀態不同步')
if backtest.get('next_signed_weights')!=result.get('production_weights') or result.get('audit_weights')!=result.get('production_weights'): errors.append('公開主選與方向模型隔離回測權重不同')
rolling=result.get('rolling_weight_adjustment') or {}
if rolling.get('production_weights')!=result.get('production_weights') or rolling.get('production_ensemble_weights')!=ensemble or rolling.get('anchor_ensemble_weights')!=selection.get('ensemble_members') or rolling.get('updates')!=360 or rolling.get('method')!='thirty_polarity_models_360_draw_five_member_weight_consensus' or rolling.get('strategy_candidate_count')!=30 or rolling.get('strategy_selection_window')!=360 or rolling.get('strategy_consensus_member_count')!=5: errors.append('最新開獎錯誤沒有觸發三十組方向模型、三百六十期選擇窗與五組權重共識')
rate_selection=rolling.get('learning_rate_selection') or {}
if rate_selection.get('candidate_count')!=30 or rate_selection.get('learning_rate_candidate_count')!=6 or rate_selection.get('boundary_blend_candidate_count')!=5 or not rate_selection.get('holdout_not_used'): errors.append('舊邊界診斷未保持隔離')
if backtest.get('next_signed_weights')!=result.get('production_weights') or backtest.get('rolling_update_count')!=360: errors.append('隔離回測沒有重演方向模型逐期選擇')
if backtest.get('strategy_candidate_count')!=30 or backtest.get('strategy_selection_window')!=360 or backtest.get('strategy_consensus_member_count')!=5: errors.append('隔離回測缺少三十組方向模型、三百六十期選擇窗或五組权重共识')
if health.get('polarity_selection_window')!=360 or health.get('polarity_consensus_member_count')!=5: errors.append('公開健康檔未同步三百六十期五組權重共識')
stability=backtest.get('anchor_stability') or {}
if stability.get('selected') not in ('穩定冠軍','每日挑戰者') or rolling.get('anchor_stability')!=stability or health.get('anchor_stability')!=stability or rolling.get('anchor_weights')!=result.get('production_anchor_weights') or health.get('production_anchor_weights')!=result.get('production_anchor_weights'): errors.append('穩定冠軍與每日挑戰模型守門未完整同步')
if not backtest.get('catastrophic_guard_enabled'): errors.append('公開結果未啟用災難失準保護')
if backtest.get('single_specialist_enabled'): errors.append('公開結果仍啟用已證明拖累的短窗單碼重排')
if backtest.get('catastrophic_guard_execution_enabled') or backtest.get('catastrophic_guard_application_count')!=0: errors.append('失準旋轉未保持只監測或曾改動正式排序')
full_scan=result.get('full_history_scan') or {}
if full_scan.get('samples')!=result.get('draw_count',0)-320: errors.append('公開結果的全歷史逐期掃描期數錯誤')
if full_scan.get('validation_eligible') and not full_scan.get('ranking_direction_valid'): warnings.append('可驗證的全歷史逐期排序方向未通過')
if str(version.get('latest_period'))!=str(official['period']) or version.get('latest_draw_date')!=official['draw_date']: errors.append('手機版本檔未同步官方最新期別')
if not settlements:
    errors.append('公開頁缺少每期命中檢討結算檔')
else:
    review=settlements[-1]
    if review.get('target_draw_date')!=official['draw_date'] or str(review.get('official_period'))!=str(official['period']): errors.append('最新命中檢討未對應官方最新期別')
    if review.get('review_status')!='completed_from_pre_draw_seal' or len(review.get('actual_rankings') or [])!=5 or len(review.get('module_review') or [])!=len(result.get('production_weights') or {}): errors.append('最新命中檢討缺少實際排名或錯誤模組分析')
    expected_top5_hits=sorted(set(review.get('actual_numbers') or []).intersection(review.get('top5_published') or []))
    if len(review.get('top5_published') or [])!=5 or sorted(review.get('top5_hits') or [])!=expected_top5_hits: errors.append('最新命中檢討缺少或算錯前5命中資料')
    actual_boundary=sorted(x.get('number') for x in (review.get('actual_rankings') or []) if 10<=int(x.get('rank',99))<=15)
    if sorted(review.get('rank10_15_hits') or [])!=actual_boundary or review.get('boundary_review_status') not in ('triggered_and_recalculated','checked_no_rank_10_15_hit'): errors.append('最新命中檢討缺少第10至15名偏移檢查')
    if any(any(key not in module for key in ('boundary_actual_mean','false_top9_mean','boundary_discrimination_gap','boundary_error_flag')) for module in (review.get('module_review') or [])): errors.append('最新命中檢討缺少前9邊界逐模組比較')
    if not (review.get('data_integrity') or {}).get('no_post_draw_substitution'): errors.append('命中檢討未禁止開獎後換號')
    if not (review.get('rolling_adjustment') or {}).get('completed') or (review.get('rolling_adjustment') or {}).get('candidate_count')!=286 or (review.get('rolling_adjustment') or {}).get('boundary_parameter_candidate_count')!=30: errors.append('命中檢討後沒有完成286組權重與30組前9邊界重算')
    if not health.get('settled_previous'): errors.append('健康檔沒有標示最新命中檢討完成')
    expected_condition=(len(review.get('top9_hits') or [])==0 and float(review.get('average_actual_rank') or 0)>=22)
    expected_guard=expected_condition and bool(backtest.get('catastrophic_guard_policy_recommends'))
    if bool(backtest.get('catastrophic_guard_current_condition'))!=expected_condition or bool(health.get('catastrophic_guard_current_condition'))!=expected_condition: errors.append('災難失準條件沒有依最新封存檢討同步')
    if bool(backtest.get('catastrophic_guard_current_trigger'))!=expected_guard or bool(health.get('catastrophic_guard_current_trigger'))!=expected_guard: errors.append('災難失準保護沒有依最新封存檢討同步啟動')
    base=list(backtest.get('next_unguarded_ranked') or [])
    if expected_guard and len(base)==39:
        previous=set(review.get('actual_numbers') or [])
        qualified=previous.intersection(base[:9]);blocked=previous-qualified
        rotated=base[12:]+base[:12]
        first=base[0]
        eligible=[number for number in rotated if number!=first and number not in blocked]
        front=[first]+eligible[:8];expected_ranked=front+[number for number in rotated if number not in front]
        if expected_ranked[0]!=first: errors.append('災難失準保護錯誤換掉原始第1名')
    else:
        expected_ranked=base
    if result.get('ranked_all')!=expected_ranked or backtest.get('next_ranked')!=expected_ranked: errors.append('公開正式排序未套用災難失準保護')
visible_pages={}
for name,page in pages.items():
    visible=re.sub(r'(?is)<(?:style|script)\b[^>]*>.*?</(?:style|script)>',' ',page)
    visible=html.unescape(re.sub(r'(?s)<[^>]+>',' ',visible))
    visible_pages[name]=visible
    english=sorted(set(re.findall(r'[A-Za-z][A-Za-z0-9_-]*',visible)))
    if english: errors.append(f'{name} 可見文字含英文：'+','.join(english))
    links=set(re.findall(r"href=['\"]\./([^'\"]+\.html)['\"]",page))
    if links!=set(REPORT_PAGES): errors.append(f'{name} 分頁導覽不完整')
home=visible_pages['index.html']; review_page=visible_pages['review.html']; backtest_page=visible_pages['backtest.html']; history_page=visible_pages['history.html']; models_page=visible_pages['models.html']; health_page=visible_pages['health.html']
if '本期最強1顆' not in home or '1中1' not in home or (ranked and f'{int(ranked[0]):02}' not in home): errors.append('本期預測頁未顯示1中1主選')
if any(term in home for term in ('最新一期命中結算','最後360期隔離回測','全歷史運算範圍','鐵律守門')): errors.append('本期預測頁混入其他分類資料')
if '最新一期命中結算' not in review_page or '開獎前前5正式預測' not in review_page or '前5命中資料' not in review_page or '錯誤模組與前9邊界逐項檢討' not in review_page or '第10至15名命中' not in review_page or '開獎後滾動權重重算' not in review_page or '禁止開獎後換號或補號' not in review_page: errors.append('開獎檢討分頁內容不完整')
if '最後360期隔離回測' not in backtest_page or '最近54期獨立觀察' not in backtest_page or '全歷史逐期一致性掃描' not in backtest_page: errors.append('回測驗證分頁內容不完整')
if '開獎前封存實戰紀錄' not in history_page or '前5命中資料' not in history_page or '錯誤模組與前9邊界逐項檢討' in history_page: errors.append('歷史封存分頁內容不完整或混入逐項檢討')
if '正式方向模型' not in models_page or '全系統重組' not in models_page or '五組正式權重共識' not in models_page or '穩定冠軍與每日挑戰模型' not in models_page or '連莊資格驗算規格' not in models_page or '全歷史連莊率不低於12.82%' not in models_page: errors.append('模型說明分頁內容不完整')
if '鐵律守門' not in health_page or '五組權重共識' not in health_page or '手機同步' not in health_page or '開獎後更新與自主修復' not in health_page or '兩小時修復期限' not in health_page: errors.append('系統健康分頁內容不完整')
if any('低機率' in visible or '當期預測前九' in visible for visible in visible_pages.values()): errors.append('公開分頁仍含易誤解標示或事後回算內容')
expected_direction='排序方向通過' if backtest.get('ranking_direction_valid') else '排序方向未通過'
if expected_direction not in backtest_page or expected_direction not in health_page: errors.append('回測或健康分頁未照實顯示排序方向')
if errors: raise SystemExit('鐵律看門狗失敗：'+'；'.join(errors))
print(json.dumps({'看門狗':'通過','官方期別':official['period'],'公開期別':health['latest_period'],'全歷史':True,'命中檢討':'完成','滾動候選':286,'1中1主選':result['single_published'],'模型警報':warnings,'戰報可見英文':0},ensure_ascii=False))
