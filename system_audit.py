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
from tw539_ultra import (FORMAL_FEATURE_KEYS, GLOBAL_HISTORY_BLEND, MAX_ANCHOR_MODULE_WEIGHT,
                         MODEL_SEARCH_CANDIDATE_COUNT, ROLLING_ENSEMBLE_MEMBERS,
                         ROLLING_BOUNDARY_BLEND_CANDIDATES, ROLLING_LEARNING_RATE_CANDIDATES,
                         MIN_ENSEMBLE_WEIGHT_DISTANCE, POLARITY_SELECTION_WINDOW,
                         adaptive_polarity_backtest,
                         apply_repeat_qualification, average_weights, build_number_diagnostics,
                         candidate_grid_sha256, ensemble_scores_from_features, evaluation_cases,
                         fast_case_ranking, formal_history_state, load_draws, rank_numbers,
                         ranking_direction_metrics, rolling_ensemble_direction_metrics, scores,
                         scores_from_features, select_rolling_weights, valid_ticket)
from tw539_ultra import select_rolling_learning_rate

ROOT=Path(__file__).resolve().parent
CSV=ROOT/'data'/'539.csv'
REPORTS=ROOT/'reports'
SITE=ROOT/'site'
errors=[]
warnings=[]

def equivalent(left,right,tolerance=1e-12):
    if isinstance(left,dict) and isinstance(right,dict):
        return set(left)==set(right) and all(equivalent(left[key],right[key],tolerance) for key in left)
    if isinstance(left,list) and isinstance(right,list):
        return len(left)==len(right) and all(equivalent(a,b,tolerance) for a,b in zip(left,right))
    if isinstance(left,(int,float)) and isinstance(right,(int,float)):
        return abs(float(left)-float(right))<=tolerance
    return left==right

def fail(message):
    errors.append(message)

def warn(message):
    warnings.append(message)

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
ensemble_weights=result.get('production_ensemble_weights') or []
if not weights or not set(weights).issubset(set(FORMAL_FEATURE_KEYS)): fail('正式模型混入非全歷史或未核准特徵')
if abs(sum(abs(float(x)) for x in weights.values())-1)>1e-9: fail('正式方向模型絕對權重總和不是一')
if ensemble_weights: fail('正式排序仍錯用同質三模型共識')
if result.get('audit_weights')!=weights: fail('正式主選與隔離回測不是同一組權重')
diagnostics=result.get('weight_selection_diagnostics') or []
if len(diagnostics)!=1 or sum(bool(x.get('selected')) for x in diagnostics)!=1: fail('多區段穩定性選模紀錄不完整')
else:
    selected=diagnostics[0]
    validation=selected.get('validation') or {}
    if selected.get('candidate_count')!=MODEL_SEARCH_CANDIDATE_COUNT or MODEL_SEARCH_CANDIDATE_COUNT<200: fail('多模組候選組合搜尋數量不足')
    if selected.get('candidate_grid_sha256')!=candidate_grid_sha256(): fail('286組候選權重格指紋錯誤')
    anchor_weights=selected.get('weights') or {}
    anchor_ensemble=selected.get('ensemble_members') or []
    if result.get('anchor_ensemble_weights')!=anchor_ensemble: fail('分散錨定模型未封存')
    if selected.get('eligible_candidate_count')!=146 or selected.get('max_anchor_module_weight')!=MAX_ANCHOR_MODULE_WEIGHT: fail('均衡候選限制未正確套用')
    if len(anchor_ensemble)!=ROLLING_ENSEMBLE_MEMBERS or selected.get('ensemble_member_count')!=ROLLING_ENSEMBLE_MEMBERS: fail('前三均衡共識模型缺失')
    if any(max(member.values())>MAX_ANCHOR_MODULE_WEIGHT+1e-12 for member in anchor_ensemble): fail('錨定模型仍有單一模組過度集中')
    for index,member in enumerate(anchor_ensemble):
        for other in anchor_ensemble[:index]:
            if sum(abs(member[key]-other[key]) for key in FORMAL_FEATURE_KEYS)<MIN_ENSEMBLE_WEIGHT_DISTANCE-1e-12: fail('三個錨定模型仍高度同質')
    rolling_adjustment=result.get('rolling_weight_adjustment') or {}
    if rolling_adjustment.get('anchor_weights')!=average_weights(anchor_ensemble) or rolling_adjustment.get('anchor_ensemble_weights')!=anchor_ensemble: fail('三模型錨定權重與逐期滾動未銜接')
    if rolling_adjustment.get('production_weights')!=weights or rolling_adjustment.get('production_ensemble_weights')!=ensemble_weights: fail('三模型終點權重與正式主選未銜接')
    if rolling_adjustment.get('updates')!=360 or rolling_adjustment.get('method')!='thirty_polarity_models_ninety_draw_walk_forward_selection': fail('最新開獎錯誤沒有觸發三十組方向模型逐期重選')
    if rolling_adjustment.get('strategy_candidate_count')!=30 or rolling_adjustment.get('strategy_selection_window')!=POLARITY_SELECTION_WINDOW: fail('方向模型數或九十期選擇窗錯誤')
    if validation.get('samples')!=360: fail('前段滾動校正不是三百六十期')
    if selected.get('method')!='balanced_three_model_consensus_all_history_286_grid': fail('正式權重不是均衡三模型共識與長歷史複驗')
    calibration=selected.get('calibration_window') or {}; holdout_window=selected.get('holdout_window') or {}
    if calibration.get('samples')!=360 or holdout_window.get('samples')!=360: fail('滾動校正或隔離窗口期數錯誤')
    long_window=selected.get('long_history_selection_window') or {}
    if long_window.get('samples',0)<1000 or long_window.get('folds')!=9: fail('更早長歷史九段複驗樣本不足')
    if calibration.get('last_period')!=(result.get('model_selection_cutoff') or {}).get('period'): fail('模型校正截止期沒有同步滾動窗口')
    cutoff_index=next((i for i,x in enumerate(draws) if x['period']==calibration.get('last_period') and x['date']==calibration.get('last_date')),-1)
    if cutoff_index<0 or len(draws)-cutoff_index-1!=360: fail('滾動校正截止點與末段三百六十期沒有完全隔離')
    expected_weights,expected_diagnostics,expected_selection=select_rolling_weights(draws,360)
    if expected_weights!=anchor_weights: fail('重新搜尋286組後的最佳錨定權重不同')
    expected_anchor_ensemble=expected_diagnostics[0].get('ensemble_members') or []
    if expected_anchor_ensemble!=anchor_ensemble: fail('重新搜尋後的前三均衡模型不同')
    expected_rate,expected_rate_selection=select_rolling_learning_rate(draws,anchor_ensemble,360)
    if not expected_rate_selection.get('holdout_not_used'): fail('舊邊界診斷使用了隔離答案')
    if expected_rate_selection.get('candidate_count')!=len(ROLLING_LEARNING_RATE_CANDIDATES)*len(ROLLING_BOUNDARY_BLEND_CANDIDATES): fail('學習幅度與前9邊界參數未完整交叉搜尋')
    expected_diagnostics[0]['learning_rate_selection']=expected_rate_selection
    expected_diagnostics[0]['production_weights_after_rolling']=weights
    expected_diagnostics[0]['production_ensemble_after_rolling']=ensemble_weights
    if not equivalent(expected_diagnostics,diagnostics): fail('滾動校正診斷無法完整重現')
    if (result.get('rolling_calibration') or {}).get('leaderboard')!=expected_selection.get('leaderboard'): fail('滾動候選排行榜無法重現')
    for case in evaluation_cases(draws,len(draws)-50,len(draws)):
        raw_case=scores_from_features(case['features'],weights)
        standard=rank_numbers(apply_repeat_qualification(raw_case,case['features'],weights,case['previous_numbers'],case['seed'],case['repeat_exposure'],case['repeat_hits'])[0],case['seed'])
        if fast_case_ranking(case,weights)!=standard: fail('加速校正排序與完整排序不等價')

history_payload='|'.join(f"{x['period']}:{x['date']}:{','.join(map(str,x['nums']))}" for x in draws)
database_hash=hashlib.sha256(history_payload.encode()).hexdigest()
if coverage.get('database_sha256')!=database_hash: fail('最新結果的歷史資料庫指紋不符')
if health.get('history_database_sha256')!=database_hash or site_health.get('history_database_sha256')!=database_hash: fail('健康檔的歷史資料庫指紋不符')

ranked_all=result.get('ranked_all') or []
ranked=result.get('ranked_top15') or []
if len(ranked_all)!=39 or set(ranked_all)!=set(range(1,40)) or ranked!=ranked_all[:15]: fail('開獎前完整39碼排序缺失或前15不同步')
if len(ranked)!=15 or len(set(ranked))!=15 or any(not 1<=int(n)<=39 for n in ranked): fail('前十五名資料錯誤')
elif result.get('single_candidate')!=ranked[0] or result.get('single_published')!=ranked[0]: fail('1中1主選未固定產出並公開')
if ranked!=rank_numbers(scores(draws,weights),latest['period'])[:15]: fail('正式方向模型排名不可重現')
overlap=result.get('previous_draw_overlap_audit') or {}
if overlap.get('method')!='model_score_with_repeat_qualification' or overlap.get('previous_numbers')!=list(latest['nums']): fail('上一期號碼檢查設定錯誤')
if overlap.get('top5_overlap')!=len(set(ranked[:5])&set(latest['nums'])) or overlap.get('top9_overlap')!=len(set(ranked[:9])&set(latest['nums'])): fail('上一期號碼重複數與正式排名不同步')
if overlap.get('full_previous_draw_copied_into_top9') or set(latest['nums']).issubset(ranked[:9]): fail('正式模型仍整批複製上一期號碼')
current_state=formal_history_state(draws); current_features=current_state.features()
raw_current=scores_from_features(current_features,weights)
qualified_scores,recalculated_repeat=apply_repeat_qualification(
    raw_current,current_features,weights,latest['nums'],latest['period'],
    current_state.repeat_exposure,current_state.repeat_hits)
if result.get('repeat_qualification')!=recalculated_repeat: fail('連莊資格沒有從正式模型獨立重算')
recalculated_ranking=rank_numbers(qualified_scores,latest['period'])
if ranked_all!=recalculated_ranking: fail('連莊資格後完整39碼排名與公開排名不同')
recalculated_number_diagnostics=build_number_diagnostics(recalculated_ranking,qualified_scores,raw_current,current_features,weights)
if result.get('number_diagnostics')!=recalculated_number_diagnostics: fail('開獎前39碼模組貢獻無法重現')
if result.get('single_selection_evidence')!=recalculated_number_diagnostics[0]: fail('最強獨隻缺少可重現的模組證據')
repeat_by_number={x.get('number'):x for x in (result.get('repeat_qualification') or [])}
for n in set(ranked[:9])&set(latest['nums']):
    if not (repeat_by_number.get(n) or {}).get('qualified'): fail(f'上一期號碼{n:02}未通過連莊資格卻列入前9')
    if not (repeat_by_number.get(n) or {}).get('repeat_backtest_pass'): fail(f'上一期號碼{n:02}個別連莊回測未達標卻列入前9')
if not (result.get('release_policy') or {}).get('official_release_allowed'): fail('主選公開狀態遭門檻封鎖')

target=datetime.strptime(latest['date'],'%Y-%m-%d').date()+timedelta(days=1)
while target.weekday()==6: target+=timedelta(days=1)
if result.get('target_draw_date')!=target.isoformat(): fail('預測目標日期錯誤')
seal=result.get('pre_draw_seal') or {}; sealed_payload=seal.get('sealed_payload') or {}
seal_hash=hashlib.sha256(json.dumps(sealed_payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
if seal.get('algorithm')!='sha256' or seal.get('sha256')!=seal_hash or not seal.get('no_post_draw_substitution'): fail('開獎前封存雜湊或禁止事後換號旗標錯誤')
if sealed_payload.get('based_on_period')!=latest['period'] or sealed_payload.get('target_draw_date')!=target.isoformat(): fail('開獎前封存期別日期錯誤')
if sealed_payload.get('history_database_sha256')!=coverage.get('database_sha256') or sealed_payload.get('ranked_all')!=ranked_all or sealed_payload.get('number_diagnostics')!=result.get('number_diagnostics'): fail('開獎前封存內容與公開結果不同步')
if sealed_payload.get('production_ensemble_weights')!=ensemble_weights: fail('開獎前封存缺少三模型終點權重')
if sealed_payload.get('rolling_boundary_blend')!=(result.get('rolling_weight_adjustment') or {}).get('boundary_blend'): fail('開獎前封存缺少前9邊界占比')
if result.get('recalculation_fingerprint')!=seal_hash[:16]: fail('預測重算指紋沒有取自完整開獎前封存資料')

tickets=[tuple(int(n) for n in ticket) for ticket in (result.get('tickets') or [])]
if not tickets or len(tickets)!=len(set(tickets)): fail('精選組合缺失或重複')
for ticket in tickets:
    if len(ticket)!=5 or len(set(ticket))!=5 or not valid_ticket(tuple(sorted(ticket))): fail('精選組合未通過牌型限制')
for index,ticket in enumerate(tickets):
    if any(len(set(ticket)&set(other))>3 for other in tickets[:index]): fail('精選組合彼此重疊過高')
full_ranking=rank_numbers(scores(draws,weights),latest['period'])
forced_exclusion=set(full_ranking[-15:])
if set(result.get('forced_ticket_exclusions') or [])!=forced_exclusion: fail('強制投注排除名單與正式排序不同步')
for ticket in tickets:
    if set(ticket)&forced_exclusion: fail('推薦牌組含強制投注排除號碼')
backtest=result.get('backtest') or {}
if backtest.get('samples')!=360: fail('隔離回測不是三百六十期')
if sum(int(v) for v in (backtest.get('top9_hit_distribution') or {}).values())!=backtest.get('samples'): fail('前9逐期命中分布加總錯誤')
for key in ('single_rate','single_random_baseline','single_wilson_lower95'):
    if not 0<=float(backtest.get(key,-1))<=1: fail(f'隔離回測數值錯誤：{key}')
for key in ('bottom1_hits','bottom5_avg_hits','top9_hits','rank10_15_hits','rank10_15_avg_hits','top9_capture_rate','top9_slot_hit_rate','rank10_15_slot_hit_rate','boundary_control_valid','bottom9_avg_hits','avg_actual_rank','ranking_direction_valid','top5_at_least_2_rate','top9_at_least_2_rate'):
    if key not in backtest: fail(f'隔離回測缺少高低分方向欄位：{key}')
calculated_direction=(backtest.get('top5_avg_hits',0)>backtest.get('bottom5_avg_hits',0)
                      and backtest.get('top9_avg_hits',0)>backtest.get('bottom9_avg_hits',0)
                      and backtest.get('top9_slot_hit_rate',0)>backtest.get('rank10_15_slot_hit_rate',0)
                      and backtest.get('avg_actual_rank',99)<20)
if bool(backtest.get('ranking_direction_valid'))!=calculated_direction: fail('高低分方向判定與實際數據不符')
if bool(backtest.get('single_direction_valid'))!=(backtest.get('single_hits',0)>backtest.get('bottom1_hits',0)): fail('1中1方向判定與實際數據不符')
if not calculated_direction: warn('校正後正式模型的最後三百六十期排序方向未通過，已保留模型警報但不得阻斷官方資料發布')
if backtest.get('next_signed_weights')!=weights or backtest.get('rolling_update_count')!=360: fail('隔離回測終點方向與正式主選不同步')
recalculated_holdout=adaptive_polarity_backtest(draws,average_weights(anchor_ensemble),360,POLARITY_SELECTION_WINDOW)
for key in ('samples','single_hits','bottom1_hits','top5_avg_hits','bottom5_avg_hits','top9_hits','rank10_15_hits','top15_hits','top9_avg_hits','rank10_15_avg_hits','top15_avg_hits','top9_capture_rate','top9_slot_hit_rate','rank10_15_slot_hit_rate','boundary_control_valid','bottom9_avg_hits','avg_actual_rank','ranking_direction_valid','top5_at_least_2_rate','top9_at_least_2_rate','next_signed_weights','next_ranked','rolling_update_count','rolling_path_sha256','method'):
    if not equivalent(recalculated_holdout.get(key),backtest.get(key)): fail(f'最後三百六十期方向模型獨立重算不符：{key}')
full_scan=result.get('full_history_scan') or {}
recalculated_full=ranking_direction_metrics(draws,weights,320,len(draws))
for key in ('samples','single_hits','bottom1_hits','top5_avg_hits','bottom5_avg_hits','top9_hits','rank10_15_hits','top15_hits','top9_avg_hits','rank10_15_avg_hits','top15_avg_hits','top9_capture_rate','boundary_control_valid','bottom9_avg_hits','avg_actual_rank','ranking_direction_valid'):
    if recalculated_full.get(key)!=full_scan.get(key): fail(f'全歷史逐期掃描獨立重算不符：{key}')
if full_scan.get('samples')!=len(draws)-320: fail('全歷史逐期一致性掃描期數錯誤')
if full_scan.get('validation_eligible') and not full_scan.get('ranking_direction_valid'): warn('可驗證的全歷史逐期排序方向未通過')

if site_result!=result: fail('手機結果與戰報結果不同步')
if site_health!=health: fail('手機健康檔與戰報健康檔不同步')
for label,item in (('戰報健康檔',health),('手機健康檔',site_health)):
    if item.get('latest_period')!=latest['period'] or item.get('latest_draw_date')!=latest['date']: fail(f'{label}期別日期錯誤')
    if not item.get('full_history_mode'): fail(f'{label}不是全歷史模式')
    if not item.get('model_release_allowed') or not item.get('single_release_allowed'): fail(f'{label}仍會封鎖主選公開')
    if not item.get('freshness_ok') or latest['date']<expected_latest_date(): fail(f'{label}資料新鮮度錯誤')
    if bool(item.get('ranking_direction_valid'))!=bool(backtest.get('ranking_direction_valid')): fail(f'{label}未同步排序方向狀態')
    if item.get('rank10_15_avg_hits')!=backtest.get('rank10_15_avg_hits') or item.get('top9_capture_rate')!=backtest.get('top9_capture_rate') or bool(item.get('boundary_control_valid'))!=bool(backtest.get('boundary_control_valid')): fail(f'{label}未同步前9邊界狀態')
if version.get('latest_period')!=latest['period'] or version.get('latest_draw_date')!=latest['date']: fail('手機版本檔期別日期錯誤')

page_rules={
    'index.html':{
        'required':('本期分級主選','1中1','2中1～2','3中1～3','5中2～3','9中3～5','本期前15名單一明細','本期推薦牌組','本期投注排除','上一期號碼連莊資格','相對指數（非機率）','不做補位'),
        'forbidden':('最新一期命中結算','最後360期隔離回測','全歷史運算範圍','鐵律守門')},
    'backtest.html':{
        'required':('最後360期隔離回測','前後段方向對照','前9逐期命中分布','最近54期獨立觀察','全歷史逐期一致性掃描','禁止用同一期開獎結果改寫同一期預測'),
        'forbidden':('本期正式預測','最新一期命中結算','開獎前封存實戰紀錄','正式方向模型')},
    'review.html':{
        'required':('最新一期命中結算','實際開獎號碼原始排名','錯誤模組與前9邊界逐項檢討','第10至15名命中','開獎後滾動權重重算','禁止開獎後換號或補號'),
        'forbidden':('本期正式預測','最後360期隔離回測','開獎前封存實戰紀錄','全歷史運算範圍')},
    'history.html':{
        'required':('開獎前封存實戰紀錄','開獎前1中1','開獎前前9','主選結果','第10至15名命中'),
        'forbidden':('本期正式預測','錯誤模組與前9邊界逐項檢討','最後360期隔離回測','正式方向模型')},
    'models.html':{
        'required':('全歷史運算範圍','全歷史核心占比','正式方向模型','多模組校正規格','連莊資格驗算規格','相對指數至少75','全歷史連莊率不低於12.82%','不做補位'),
        'forbidden':('本期正式預測','最新一期命中結算','最後360期隔離回測','開獎前封存實戰紀錄')},
    'health.html':{
        'required':('目前資料狀態','鐵律守門','模型健康與公開狀態','自動重新運算','手機同步'),
        'forbidden':('本期正式預測','最新一期命中結算','最後360期隔離回測','正式方向模型')},
}
nav_files=set(page_rules)
for folder in (REPORTS,SITE):
    for filename,rules in page_rules.items():
        path=folder/filename
        if not path.exists():
            fail(f'{folder.name} 缺少分類分頁：{filename}')
            continue
        page=path.read_text(encoding='utf-8')
        visible=visible_text(path)
        english=sorted(set(re.findall(r'[A-Za-z][A-Za-z0-9_-]*',visible)))
        if english: fail(f'{folder.name}/{filename} 可見文字含英文：'+','.join(english))
        for term in rules['required']:
            if term not in visible: fail(f'{folder.name}/{filename} 缺少：{term}')
        for term in rules['forbidden']:
            if term in visible: fail(f'{folder.name}/{filename} 分類混入：{term}')
        links=set(re.findall(r"href=['\"]\./([^'\"]+\.html)['\"]",page))
        if links!=nav_files: fail(f'{folder.name}/{filename} 分頁導覽不完整')
        if '低機率' in visible or '當期預測前九' in visible: fail(f'{folder.name}/{filename} 仍含易誤解標示或事後回算內容')
legacy=visible_text(REPORTS/'最新539科學預測戰報.html')
if legacy!=visible_text(REPORTS/'index.html'): fail('相容戰報入口與本期預測頁不同步')
if ranked and f'{int(ranked[0]):02}' not in visible_text(SITE/'index.html'): fail('本期預測頁未顯示當期1中1主選')
generated_visible=str(result.get('generated_at',''))[:16].replace('T',' ')
if generated_visible and generated_visible not in visible_text(SITE/'index.html'): fail('本期預測頁產生時間未同步台灣時區')
expected_direction='排序方向通過' if backtest.get('ranking_direction_valid') else '排序方向未通過'
if expected_direction not in visible_text(SITE/'backtest.html') or expected_direction not in visible_text(SITE/'health.html'):
    fail('回測或健康分頁未照實顯示高低分方向')

service=(SITE/'service-worker.js').read_text(encoding='utf-8')
sync=(SITE/'mobile-sync.js').read_text(encoding='utf-8')
if "cache:'no-store'" not in service or 'system-health.json' not in service: fail('手機快取可能保留過期資料')
if 'setInterval(checkVersion,30000)' not in sync: fail('手機每三十秒同步檢查已損壞')

history_file=REPORTS/'prediction-history.jsonl'
try:
    records=[json.loads(line) for line in history_file.read_text(encoding='utf-8').splitlines() if line.strip()]
    match=[x for x in records if x.get('recalculation_fingerprint')==result.get('recalculation_fingerprint')]
    if len({x.get('target_draw_date') for x in records})!=len(records): fail('預測歷史含同日未公開中間版本')
    if len(match)!=1 or match[-1].get('single_published')!=result.get('single_published'): fail('預測歷史未唯一保存當期公開主選')
except Exception as exc: fail(f'預測歷史無法驗證：{exc}')

settlements=REPORTS/'published-settlements.jsonl'; site_settlements=SITE/'published-settlements.jsonl'
if not settlements.exists() or not site_settlements.exists():
    fail('命中檢討結算檔缺失')
else:
    try:
        report_rows=[json.loads(line) for line in settlements.read_text(encoding='utf-8').splitlines() if line.strip()]
        mobile_rows=[json.loads(line) for line in site_settlements.read_text(encoding='utf-8').splitlines() if line.strip()]
        if report_rows!=mobile_rows or not report_rows: fail('手機命中檢討結算檔未同步或為空')
        latest_review=report_rows[-1]
        if latest_review.get('target_draw_date')!=latest['date'] or latest_review.get('official_period')!=latest['period']: fail('最新命中檢討沒有對應最新開獎')
        for item in report_rows:
            if item.get('single_published') is None or item.get('single_hit') not in (True,False) or len(item.get('top5_published') or [])!=5: fail('已結算紀錄缺少開獎前封存主選或前5')
            sealed=[x for x in records if x.get('target_draw_date')==item.get('target_draw_date') and x.get('recalculation_fingerprint')==item.get('fingerprint')]
            if len(sealed)!=1: fail('已結算紀錄沒有唯一對應的開獎前正式封存')
            if item.get('review_status')!='completed_from_pre_draw_seal' or not item.get('rolling_recalculation_required'): fail('已結算紀錄沒有完成開獎前封存命中檢討')
            if len(item.get('actual_rankings') or [])!=5 or len(item.get('module_review') or [])!=len(weights): fail('命中檢討缺少實際號碼排名或逐模組檢討')
            if item.get('target_draw_date','')>='2026-07-27':
                actual_boundary=sorted(x.get('number') for x in (item.get('actual_rankings') or []) if 10<=int(x.get('rank',99))<=15)
                if sorted(item.get('rank10_15_hits') or [])!=actual_boundary: fail('命中檢討的第10至15名偏移紀錄錯誤')
                if item.get('boundary_review_status') not in ('triggered_and_recalculated','checked_no_rank_10_15_hit'): fail('命中檢討缺少前9邊界狀態')
                for module in item.get('module_review') or []:
                    if any(key not in module for key in ('boundary_actual_mean','false_top9_mean','boundary_discrimination_gap','boundary_error_flag')): fail('命中檢討缺少前9邊界逐模組比較')
            if not (item.get('data_integrity') or {}).get('no_post_draw_substitution'): fail('命中檢討沒有禁止事後換號')
            if len(str(item.get('pre_draw_seal_sha256') or item.get('legacy_reconstruction_sha256') or ''))!=64 or len(str(item.get('review_evidence_sha256') or ''))!=64: fail('命中檢討證據雜湊缺失')
            adjustment=item.get('rolling_adjustment') or {}
            if not adjustment.get('completed') or adjustment.get('candidate_count')!=MODEL_SEARCH_CANDIDATE_COUNT: fail('開獎後沒有重跑全部286組權重')
            if item.get('target_draw_date','')>='2026-07-27' and adjustment.get('boundary_parameter_candidate_count')!=len(ROLLING_LEARNING_RATE_CANDIDATES)*len(ROLLING_BOUNDARY_BLEND_CANDIDATES): fail('開獎後沒有重跑三十組前9邊界參數')
        if not health.get('settled_previous') or not site_health.get('settled_previous'): fail('健康檔沒有標示最新命中檢討完成')
    except Exception as exc: fail(f'已結算紀錄無法驗證：{exc}')

if errors:
    raise SystemExit('整套系統驗收失敗：'+'；'.join(dict.fromkeys(errors)))
print(json.dumps({'全面驗收':'通過','歷史期數':len(draws),'最新期別':latest['period'],'全歷史占比':'100%','1中1主選':result['single_published'],'排序方向':'通過' if backtest.get('ranking_direction_valid') else '未通過','模型警報':list(dict.fromkeys(warnings)),'戰報可見英文':0},ensure_ascii=False))
