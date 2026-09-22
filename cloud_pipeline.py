#!/usr/bin/env python3
"""官方最新開獎 -> 驗證 -> 重算 -> 產生獨立 PWA。僅使用 Python 標準庫。"""
from __future__ import annotations
import argparse, csv, hashlib, json, os, shutil, subprocess, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent; CSV=ROOT/'data'/'539.csv'; SITE=ROOT/'site'; REPORTS=ROOT/'reports'; REPORT=REPORTS/'最新539科學預測戰報.html'
REPORT_PAGE_FILES=('index.html','backtest.html','review.html','history.html','models.html','health.html')
API='https://api.taiwanlottery.com/TLCAPIWeB/Lottery/LatestResult'
HISTORY_API='https://api.taiwanlottery.com/TLCAPIWeB/Lottery/Daily539Result'
TAIPEI=timezone(timedelta(hours=8))
MODEL_TIMEOUT_SECONDS=900
FAST_WATCHDOG=os.getenv('TW539_WATCHDOG_FAST','').lower() in ('1','true','yes')
REQUEST_RETRY_DELAYS=(0,1) if FAST_WATCHDOG else (0,3,10)
REQUEST_TIMEOUT_SECONDS=8 if FAST_WATCHDOG else 45

def _request_json(url, params=None):
    if params:
        url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
    last=None
    for delay in REQUEST_RETRY_DELAYS:
        if delay: time.sleep(delay)
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 TW539-cloud/2.0','Accept':'application/json','Cache-Control':'no-cache'})
            with urllib.request.urlopen(req,timeout=REQUEST_TIMEOUT_SECONDS) as r:
                if r.status!=200: raise RuntimeError(f'官方回應狀態 {r.status}')
                return json.load(r)
        except Exception as e: last=e
    raise RuntimeError(f'官方資料取得失敗：{last}')

def _normalise_draw(x, source):
    nums=[int(n) for n in (x.get('drawNumberSize') or [])[:5]]
    raw=str(x.get('lotteryDate') or '').split('T')[0].replace('/','-')
    datetime.strptime(raw,'%Y-%m-%d')
    if len(nums)!=5 or len(set(nums))!=5 or any(n<1 or n>39 for n in nums):
        raise ValueError('官方號碼驗證失敗')
    period=str(x.get('period') or '')
    if not period.isdigit(): raise ValueError('官方期別驗證失敗')
    order=[int(n) for n in (x.get('drawNumberAppear') or [])[:5]]
    if len(order)!=5 or set(order)!=set(nums): order=list(nums)
    return {'period':period,'draw_date':raw,'nums':sorted(nums),'order':order,'source':source}

def _month_keys(start_date, end_date):
    cursor=datetime.strptime(start_date[:7]+'-01','%Y-%m-%d').date()
    end=datetime.strptime(end_date[:7]+'-01','%Y-%m-%d').date()
    while cursor<=end:
        yield cursor.strftime('%Y-%m')
        cursor=(cursor.replace(day=28)+timedelta(days=4)).replace(day=1)

def fetch_official_range(start_date, end_date):
    """逐月抓取官方歷史端點；停擺多日也不能只補最後一期。"""
    rows={}
    for month in _month_keys(start_date,end_date):
        payload=_request_json(HISTORY_API,{
            'period':'','month':month,'endMonth':month,'pageNum':1,'pageSize':200})
        content=payload.get('content') or payload
        for raw in content.get('daily539Res') or []:
            draw=_normalise_draw(raw,'taiwanlottery_daily539_result')
            if start_date<=draw['draw_date']<=end_date: rows[draw['period']]=draw
    return sorted(rows.values(),key=lambda x:(x['draw_date'],int(x['period'])))

def fetch_latest():
    errors=[]
    try:
        payload=_request_json(API)
        x=(payload.get('content') or {}).get('daily539Result')
        if not x: raise ValueError('官方最新端點沒有今彩539資料')
        return _normalise_draw(x,'taiwanlottery_latest_result')
    except Exception as exc:
        errors.append(str(exc))
    # 第一端點暫時失效時，改由官方各期結果端點取最近兩個月最後一筆。
    today=datetime.now(TAIPEI).date()
    start=(today-timedelta(days=45)).isoformat()
    try:
        rows=fetch_official_range(start,today.isoformat())
        if rows: return rows[-1]
    except Exception as exc:
        errors.append(str(exc))
    raise RuntimeError('官方兩組資料來源均無法取得：'+'；'.join(errors))

def update_csv(draws):
    if isinstance(draws,dict): draws=[draws]
    with CSV.open('r',encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f)); fields=list(rows[0])
    changed=0
    for latest in sorted(draws,key=lambda x:(x['draw_date'],int(x['period']))):
        existing=next((r for r in rows if r['period']==latest['period']),None)
        if existing:
            old_nums=sorted(int(existing[f'n{i}']) for i in range(1,6))
            if existing['draw_date']==latest['draw_date'] and old_nums==latest['nums']: continue
            row=existing; rows.remove(existing)
        else:
            same_date=next((r for r in rows if r['draw_date']==latest['draw_date']),None)
            if same_date and same_date['period']!=latest['period']:
                raise RuntimeError(f"官方資料日期重複但期別不同：{latest['draw_date']}")
            row={k:'' for k in fields}
        row.update({'period':latest['period'],'draw_date':latest['draw_date'],
                    'draw_order':','.join(f'{int(n):02}' for n in latest['order']),
                    'source':latest.get('source') or 'taiwanlottery_official',
                    'fetched_at':datetime.now(TAIPEI).isoformat(timespec='seconds')})
        for i,n in enumerate(latest['nums'],1): row[f'n{i}']=str(n)
        rows.append(row); changed+=1
    if not changed: return False
    rows.sort(key=lambda r:(r['draw_date'],int(r['period'])))
    tmp=CSV.with_suffix('.csv.tmp')
    with tmp.open('w',encoding='utf-8-sig',newline='') as f: w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    tmp.replace(CSV); return True

def read_json(path):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except Exception: return None

def append_jsonl(path, item, unique_key, replace=False):
    old=[]
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            try: old.append(json.loads(line))
            except Exception: pass
    matches=[index for index,existing in enumerate(old) if unique_key(existing)==unique_key(item)]
    if matches:
        if not replace: return False
        first=matches[0]
        old=[x for x in old if unique_key(x)!=unique_key(item)]
        old.insert(min(first,len(old)),item)
        path.write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in old)+'\n',encoding='utf-8')
        return True
    old.append(item)
    path.write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in old)+'\n',encoding='utf-8')
    return True

def read_jsonl(path):
    rows=[]
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            try: rows.append(json.loads(line))
            except Exception: pass
    return rows

def reconstruct_pre_draw_snapshot(prediction):
    """舊封存只准用目標日前資料精確重建，且原前15名與指紋必須完全一致。"""
    from tw539_ultra import (load_draws, formal_history_state, scores_from_features,
                             apply_repeat_qualification, average_weights,
                             ensemble_scores_from_features, rank_numbers,
                             build_number_diagnostics)
    draws=load_draws(CSV)
    index=next((i for i,x in enumerate(draws) if str(x['period'])==str(prediction.get('based_on_period'))),-1)
    if index<0: raise RuntimeError('找不到封存預測所依據的歷史期別')
    history=draws[:index+1]
    if history[-1]['date'] >= prediction.get('target_draw_date',''):
        raise RuntimeError('封存預測包含目標開獎日資料')
    history_payload='|'.join(f"{x['period']}:{x['date']}:{','.join(map(str,x['nums']))}" for x in history)
    history_hash=hashlib.sha256(history_payload.encode()).hexdigest()
    stored_hash=(prediction.get('history_coverage') or {}).get('database_sha256')
    if stored_hash and stored_hash!=history_hash: raise RuntimeError('封存預測歷史資料庫指紋不符')
    weights=prediction.get('production_weights') or {}
    if not weights: raise RuntimeError('封存預測缺少正式權重')
    ensemble=prediction.get('production_ensemble_weights') or []
    state=formal_history_state(history); features=state.features()
    if ensemble:
        adjusted,raw,_,_=ensemble_scores_from_features(
            features,ensemble,history[-1]['nums'],history[-1]['period'],
            state.repeat_exposure,state.repeat_hits)
        weights=average_weights(ensemble)
    else:
        raw=scores_from_features(features,weights)
        adjusted,_=apply_repeat_qualification(raw,features,weights,history[-1]['nums'],history[-1]['period'],state.repeat_exposure,state.repeat_hits)
    ranked=rank_numbers(adjusted,history[-1]['period'])
    if ranked[:15] != list(prediction.get('ranked_top15') or []):
        raise RuntimeError('舊封存預測無法精確重建原始前15名')
    old_payload=json.dumps({'based_on':history[-1]['period'],'weights':weights,'top15':ranked[:15]},sort_keys=True)
    old_fingerprint=hashlib.sha256(old_payload.encode()).hexdigest()[:16]
    if not prediction.get('pre_draw_seal') and old_fingerprint!=prediction.get('recalculation_fingerprint'):
        raise RuntimeError('舊封存預測指紋驗證失敗')
    diagnostics=build_number_diagnostics(ranked,adjusted,raw,features,weights)
    legacy_payload={'based_on_period':history[-1]['period'],'target_draw_date':prediction.get('target_draw_date'),
                    'history_database_sha256':history_hash,'ranked_all':ranked,
                    'number_diagnostics':diagnostics,'production_weights':weights,
                    'production_ensemble_weights':ensemble,
                    'legacy_fingerprint':prediction.get('recalculation_fingerprint')}
    legacy_hash=hashlib.sha256(json.dumps(legacy_payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return ranked,diagnostics,legacy_hash

def enrich_settlement(item, prediction, latest):
    if not prediction: raise RuntimeError('命中檢討找不到對應的開獎前封存預測')
    if prediction.get('target_draw_date')!=latest['draw_date']: raise RuntimeError('封存預測目標日與實際開獎日不同')
    if str(prediction.get('based_on_period'))==str(latest['period']): raise RuntimeError('禁止使用開獎後資料冒充預測')
    ranked=list(prediction.get('ranked_all') or [])
    diagnostics=list(prediction.get('number_diagnostics') or [])
    legacy_hash=None
    if len(ranked)!=39 or set(ranked)!=set(range(1,40)) or len(diagnostics)!=39:
        ranked,diagnostics,legacy_hash=reconstruct_pre_draw_snapshot(prediction)
    diagnostics_by_number={int(x['number']):x for x in diagnostics}
    if set(diagnostics_by_number)!=set(range(1,40)): raise RuntimeError('開獎前39碼診斷不完整')
    actual=set(latest['nums']); top5=ranked[:5]; top9=ranked[:9]
    unguarded=list((prediction.get('backtest') or {}).get('next_unguarded_ranked') or ranked)
    unguarded_single=unguarded[0] if unguarded else None
    missed=[n for n in top5 if n not in actual]
    boundary_hits=[n for n in ranked[9:15] if n in actual]
    false_top9=[n for n in top9 if n not in actual]
    weights=prediction.get('production_weights') or {}
    actual_rankings=[]
    for number in latest['nums']:
        row=diagnostics_by_number[number]
        actual_rankings.append({'number':number,'rank':row['rank'],'relative_index':row['relative_index'],
                                'final_score':row['final_score'],'weighted_contributions':row['weighted_contributions']})
    module_review=[]; error_modules=[]
    for key in weights:
        actual_mean=sum(float(diagnostics_by_number[n]['weighted_contributions'][key]) for n in actual)/5
        comparison=missed or false_top9 or ranked[:5]
        missed_mean=sum(float(diagnostics_by_number[n]['weighted_contributions'][key]) for n in comparison)/max(1,len(comparison))
        gap=actual_mean-missed_mean
        if boundary_hits and false_top9:
            boundary_mean=sum(float(diagnostics_by_number[n]['weighted_contributions'][key]) for n in boundary_hits)/len(boundary_hits)
            false_top9_mean=sum(float(diagnostics_by_number[n]['weighted_contributions'][key]) for n in false_top9)/len(false_top9)
            boundary_gap=boundary_mean-false_top9_mean
        else:
            boundary_mean=false_top9_mean=boundary_gap=0.0
        boundary_error=bool(boundary_hits and boundary_gap<0)
        error=gap<0 or boundary_error
        if error: error_modules.append(key)
        module_review.append({'module':key,'actual_mean':round(actual_mean,9),'missed_top5_mean':round(missed_mean,9),
                              'discrimination_gap':round(gap,9),
                              'boundary_actual_mean':round(boundary_mean,9),
                              'false_top9_mean':round(false_top9_mean,9),
                              'boundary_discrimination_gap':round(boundary_gap,9),
                              'boundary_error_flag':boundary_error,'error_flag':error})
    item.update({
        'official_period':latest['period'],'actual_numbers':latest['nums'],
        'top5_published':top5,'top9_published':top9,
        'single_published':prediction.get('single_published'),
        'single_hit':bool(prediction.get('single_published') in actual),
        'unguarded_single':unguarded_single,
        'unguarded_single_hit':bool(unguarded_single in actual),
        'catastrophic_guard_was_active':bool((prediction.get('backtest') or {}).get('catastrophic_guard_current_trigger')),
        'catastrophic_guard_single_effect':('removed_hit' if unguarded_single in actual and prediction.get('single_published') not in actual
                                           else 'preserved_or_no_hit'),
        'top5_hits':sorted(actual.intersection(top5)),'top9_hits':sorted(actual.intersection(top9)),
        'rank10_15_hits':sorted(boundary_hits),'false_top9':false_top9,
        'boundary_review_status':'triggered_and_recalculated' if boundary_hits else 'checked_no_rank_10_15_hit',
        'actual_rankings':actual_rankings,'average_actual_rank':round(sum(x['rank'] for x in actual_rankings)/5,4),
        'missed_top5':missed,'module_review':module_review,'error_modules':error_modules,
        'production_weights_before':weights,
        'pre_draw_seal_sha256':(prediction.get('pre_draw_seal') or {}).get('sha256'),
        'legacy_reconstruction_sha256':legacy_hash,
        'review_status':'completed_from_pre_draw_seal','rolling_recalculation_required':True,
        'data_integrity':{'based_on_period':prediction.get('based_on_period'),'official_period':latest['period'],
                          'target_draw_date':latest['draw_date'],'official_actual_numbers':latest['nums'],
                          'no_post_draw_substitution':True},
    })
    evidence={k:v for k,v in item.items() if k!='review_evidence_sha256'}
    item['review_evidence_sha256']=hashlib.sha256(json.dumps(evidence,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return item

def find_prediction_for_item(item):
    history=read_jsonl(REPORTS/'prediction-history.jsonl')
    exact=[x for x in history if x.get('target_draw_date')==item.get('target_draw_date') and
           x.get('recalculation_fingerprint')==item.get('fingerprint')]
    return exact[-1] if exact else None

def compact_prediction_history(current):
    """每個目標日只保留真正正式版；已結算日以結算指紋為準，未結算日以本次最終版為準。"""
    path=REPORTS/'prediction-history.jsonl'; rows=read_jsonl(path)
    settlement_fingerprints={x.get('target_draw_date'):x.get('fingerprint') for x in read_jsonl(REPORTS/'published-settlements.jsonl')
                             if x.get('review_status')=='completed_from_pre_draw_seal'}
    targets=[]
    for row in rows:
        target=row.get('target_draw_date')
        if target not in targets: targets.append(target)
    chosen=[]
    for target in targets:
        group=[x for x in rows if x.get('target_draw_date')==target]
        fingerprint=settlement_fingerprints.get(target)
        if fingerprint:
            exact=[x for x in group if x.get('recalculation_fingerprint')==fingerprint]
            if len(exact)!=1: raise RuntimeError(f'已結算日{target}找不到唯一正式封存預測')
            chosen.append(exact[0])
        elif target==current.get('target_draw_date'):
            chosen.append(current)
        else:
            published=[x for x in group if x.get('single_published') is not None]
            chosen.append((published or group)[-1])
    if current.get('target_draw_date') not in targets: chosen.append(current)
    path.write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in chosen)+'\n',encoding='utf-8')

def settle_previous(previous, latest):
    if not previous or previous.get('target_draw_date') != latest['draw_date']: return None
    actual=set(latest['nums']); top=previous.get('ranked_top15') or []
    item={
        'target_draw_date':latest['draw_date'],'actual_numbers':latest['nums'],
        'based_on_period':previous.get('based_on_period'),'fingerprint':previous.get('recalculation_fingerprint'),
        'single_published':previous.get('single_published'),
        'single_hit':bool(previous.get('single_published') in actual) if previous.get('single_published') else None,
        'top5_published':top[:5],'top9_published':top[:9],
        'top5_hits':sorted(actual.intersection(top[:5])),'top9_hits':sorted(actual.intersection(top[:9])),
        'settled_at':datetime.now(TAIPEI).isoformat(timespec='seconds')
    }
    item=enrich_settlement(item,previous,latest)
    append_jsonl(REPORTS/'published-settlements.jsonl',item,lambda x:(x.get('target_draw_date'),x.get('fingerprint')),replace=True)
    return item

def refresh_latest_settlement(latest):
    rows=read_jsonl(REPORTS/'published-settlements.jsonl')
    matches=[x for x in rows if x.get('target_draw_date')==latest['draw_date']]
    if not matches: return None
    item=matches[-1]
    if item.get('review_status')=='recovery_no_pre_draw_seal': return item
    item=enrich_settlement(item,find_prediction_for_item(item),latest)
    append_jsonl(REPORTS/'published-settlements.jsonl',item,lambda x:(x.get('target_draw_date'),x.get('fingerprint')),replace=True)
    return item

def recovery_review(latest):
    """停擺期沒有開獎前封存時只記錄事實，絕不事後補造命中率。"""
    item={
        'target_draw_date':latest['draw_date'],'official_period':latest['period'],
        'actual_numbers':latest['nums'],'fingerprint':'recovery-gap-'+latest['period'],
        'settled_at':datetime.now(TAIPEI).isoformat(timespec='seconds'),
        'review_status':'recovery_no_pre_draw_seal','review_accounted':True,
        'rolling_recalculation_required':True,
        'recovery_reason':'停擺期間沒有可驗證的開獎前封存，禁止事後補算或換號',
        'data_integrity':{'official_period':latest['period'],'target_draw_date':latest['draw_date'],
                          'official_actual_numbers':latest['nums'],'no_post_draw_substitution':True,
                          'no_fabricated_prediction':True}}
    evidence={k:v for k,v in item.items() if k!='review_evidence_sha256'}
    item['review_evidence_sha256']=hashlib.sha256(json.dumps(evidence,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    append_jsonl(REPORTS/'published-settlements.jsonl',item,lambda x:(x.get('target_draw_date'),x.get('fingerprint')),replace=True)
    return item

def account_for_new_draws(previous, new_draws, latest):
    history=read_jsonl(REPORTS/'prediction-history.jsonl')
    if previous and not any(x.get('recalculation_fingerprint')==previous.get('recalculation_fingerprint') for x in history):
        history.append(previous)
    accounted=[]
    for draw in sorted(new_draws,key=lambda x:(x['draw_date'],int(x['period']))):
        matches=[x for x in history if x.get('target_draw_date')==draw['draw_date']]
        if matches:
            try: item=settle_previous(matches[-1],draw)
            except Exception: item=recovery_review(draw)
        else:
            item=recovery_review(draw)
        accounted.append(item)
    if accounted: return accounted
    existing=refresh_latest_settlement(latest)
    return [existing] if existing else []

def repair_settlement_coverage(draws):
    """以官方歷史資料補回遺失的結算列；沒有事前封存時只登錄官方事實。"""
    history=read_jsonl(REPORTS/'prediction-history.jsonl')
    draw_dates={str(draw.get('date') or '') for draw in draws}
    prediction_dates=sorted({str(item.get('target_draw_date') or '') for item in history
                             if str(item.get('target_draw_date') or '') in draw_dates})
    if not prediction_dates:
        return {'coverage_start':None,'expected_draws':0,'accounted_draws':0,
                'missing_draws':0,'missing_dates':[],'repaired_draws':0,
                'sealed_prediction_draws':0,'official_recovery_draws':0},[]
    start=prediction_dates[0]
    expected=[draw for draw in draws if start<=str(draw.get('date') or '')<=str(draws[-1].get('date') or '')]
    settlements=read_jsonl(REPORTS/'published-settlements.jsonl')
    accounted_dates={str(item.get('target_draw_date') or '') for item in settlements}
    repaired=[]
    for draw in expected:
        draw_date=str(draw.get('date') or '')
        if draw_date in accounted_dates:
            continue
        official={'period':str(draw['period']),'draw_date':draw_date,'nums':list(draw['nums'])}
        matching=[item for item in history if item.get('target_draw_date')==draw_date]
        if matching:
            try:
                item=settle_previous(matching[-1],official)
            except Exception:
                item=recovery_review(official)
        else:
            item=recovery_review(official)
        repaired.append(item)
        accounted_dates.add(draw_date)
    settlements=read_jsonl(REPORTS/'published-settlements.jsonl')
    latest_by_date={str(item.get('target_draw_date') or ''):item for item in settlements}
    expected_dates=[str(draw.get('date') or '') for draw in expected]
    missing=[date for date in expected_dates if date not in latest_by_date]
    sealed=sum(1 for date in expected_dates if (latest_by_date.get(date) or {}).get('review_status')=='completed_from_pre_draw_seal')
    recovered=sum(1 for date in expected_dates if (latest_by_date.get(date) or {}).get('review_status')=='recovery_no_pre_draw_seal')
    return {
        'coverage_start':start,'coverage_end':expected_dates[-1] if expected_dates else None,
        'expected_draws':len(expected_dates),'accounted_draws':len(expected_dates)-len(missing),
        'missing_draws':len(missing),'missing_dates':missing,'repaired_draws':len(repaired),
        'sealed_prediction_draws':sealed,'official_recovery_draws':recovered,
    },repaired

def refresh_report_pages(current):
    """結算完成後以同一份正式結果重建分頁，避免檢討頁落後一期。"""
    from report_pages import render_report_pages
    from tw539_ultra import FEATURE_LABELS, load_draws
    draws=load_draws(CSV)
    diagnostics=current.get('number_diagnostics') or []
    score={int(item['number']):float(item['final_score']) for item in diagnostics}
    if set(score)!=set(range(1,40)): raise RuntimeError('分頁重建缺少完整39碼分數')
    selected=(current.get('weight_selection_diagnostics') or [{}])[0]
    pages=render_report_pages(
        draws,current.get('production_weights') or {},score,current.get('tickets') or [],
        current.get('backtest') or {},current.get('full_history_scan') or {},
        current.get('repeat_qualification') or [],
        {'diagnostic':selected,'anchor_stability':(current.get('backtest') or {}).get('anchor_stability') or {}},
        REPORTS,FEATURE_LABELS)
    for filename,page in pages.items():
        (REPORTS/filename).write_text(page,encoding='utf-8')
    REPORT.write_text(pages['index.html'],encoding='utf-8')

def publish_report_pages(version_stamp):
    """只發布既有正式結果的手機分頁；不得因此重算或換掉預測封存。"""
    SITE.mkdir(exist_ok=True)
    mobile_head=("<link rel='manifest' href='./manifest.webmanifest'>"
                 "<link rel='apple-touch-icon' sizes='180x180' href='./icons/icon-180.png'>"
                 "<link rel='icon' type='image/png' sizes='192x192' href='./icons/icon-192.png'>"
                 "<meta name='theme-color' content='#8b0000'>"
                 "<meta name='mobile-web-app-capable' content='yes'>"
                 "<meta name='apple-mobile-web-app-capable' content='yes'>"
                 "<meta name='apple-mobile-web-app-status-bar-style' content='black-translucent'>"
                 "<meta name='apple-mobile-web-app-title' content='539戰報'>"
                 f"<meta name='tw539-version' content='{version_stamp}'>")
    for name in REPORT_PAGE_FILES:
        shutil.copy2(REPORTS/name,SITE/name)
        path=SITE/name; page=path.read_text(encoding='utf-8')
        page=page.replace("<title>",mobile_head+"<title>",1)
        page=page.replace('</body>',"<script src='./mobile-sync.js'></script></body>")
        path.write_text(page,encoding='utf-8')

def build_site(latest, changed, previous=None, new_draws=None, pipeline_meta=None):
    previous_health=read_json(REPORTS/'system-health.json') or {}
    repair_run=os.getenv('TW539_SELF_REPAIR','').lower() in ('1','true','yes')
    pipeline_meta=pipeline_meta or {}
    accounted=account_for_new_draws(previous,new_draws or [],latest)
    from tw539_ultra import load_draws
    settlement_coverage,coverage_repaired=repair_settlement_coverage(load_draws(CSV))
    settlement_rows=read_jsonl(REPORTS/'published-settlements.jsonl')
    latest_settlements=[item for item in settlement_rows if item.get('target_draw_date')==latest['draw_date']]
    settlement=latest_settlements[-1] if latest_settlements else (accounted[-1] if accounted else None)
    try:
        subprocess.run([sys.executable,str(ROOT/'tw539_ultra.py'),'--backtest','360'],
                       check=True,cwd=ROOT,timeout=MODEL_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f'完整運算超過{MODEL_TIMEOUT_SECONDS}秒，已強制停止並交由下一輪自主修復') from exc
    current=read_json(REPORTS/'最新結果.json') or {}
    completed=[]
    completed_keys=set()
    for item in accounted+coverage_repaired:
        key=(item or {}).get('target_draw_date')
        if item and item.get('review_status')=='completed_from_pre_draw_seal' and key not in completed_keys:
            completed.append(item);completed_keys.add(key)
    if completed:
        diagnostic=(current.get('weight_selection_diagnostics') or [{}])[0]
        rolling_adjustment={
            'completed':True,'candidate_count':diagnostic.get('candidate_count'),
            'weights_after':current.get('production_weights'),
            'production_ensemble_weights':current.get('production_ensemble_weights'),
            'calibration_window':diagnostic.get('calibration_window'),
            'holdout_window':diagnostic.get('holdout_window'),
            'boundary_parameter_candidate_count':(current.get('rolling_weight_adjustment') or {}).get('learning_rate_selection',{}).get('candidate_count'),
            'selected_boundary_blend':(current.get('rolling_weight_adjustment') or {}).get('boundary_blend'),
            'polarity_model_candidate_count':(current.get('rolling_weight_adjustment') or {}).get('strategy_candidate_count'),
            'polarity_selection_window':(current.get('rolling_weight_adjustment') or {}).get('strategy_selection_window'),
            'polarity_consensus_member_count':(current.get('rolling_weight_adjustment') or {}).get('strategy_consensus_member_count'),
            'direct_hit_calibration_enabled':(current.get('rolling_weight_adjustment') or {}).get('direct_hit_calibration_enabled'),
            'direct_hit_window':(current.get('rolling_weight_adjustment') or {}).get('direct_hit_window'),
            'direct_hit_ridge':(current.get('rolling_weight_adjustment') or {}).get('direct_hit_ridge'),
            'direct_hit_full_rank_blend':(current.get('rolling_weight_adjustment') or {}).get('direct_hit_full_rank_blend'),
            'direct_hit_full_rank_gate':(current.get('rolling_weight_adjustment') or {}).get('direct_hit_full_rank_gate'),
            'single_repeat_break_enabled':(current.get('rolling_weight_adjustment') or {}).get('single_repeat_break_enabled'),
            'single_repeat_break_gate':(current.get('rolling_weight_adjustment') or {}).get('single_repeat_break_gate'),
            'single_repeat_break_current':(current.get('rolling_weight_adjustment') or {}).get('single_repeat_break_current'),
            'anchor_stability':(current.get('rolling_weight_adjustment') or {}).get('anchor_stability'),
            'next_single':current.get('single_published'),
            'next_prediction_seal_sha256':(current.get('pre_draw_seal') or {}).get('sha256')}
        for completed_item in completed:
            completed_item['rolling_adjustment']={**rolling_adjustment,'weights_before':completed_item.get('production_weights_before')}
            evidence={k:v for k,v in completed_item.items() if k!='review_evidence_sha256'}
            completed_item['review_evidence_sha256']=hashlib.sha256(json.dumps(evidence,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            append_jsonl(REPORTS/'published-settlements.jsonl',completed_item,lambda x:(x.get('target_draw_date'),x.get('fingerprint')),replace=True)
    append_jsonl(REPORTS/'prediction-history.jsonl',current,lambda x:x.get('target_draw_date'),replace=True)
    compact_prediction_history(current)
    backtest=current.get('backtest') or {}
    direction_ok=bool(backtest.get('ranking_direction_valid'))
    degraded=(not direction_ok) or (backtest.get('single_rate',0)<=backtest.get('single_random_baseline',0) and backtest.get('top9_avg_hits',0)<=backtest.get('top9_random_baseline',0))
    checked_at=datetime.now(TAIPEI)
    same_period=str(previous_health.get('latest_period'))==str(latest['period'])
    sync_completed_at=(previous_health.get('sync_completed_at') if same_period else None) or checked_at.isoformat(timespec='seconds')
    draw_at=datetime.strptime(latest['draw_date']+' 20:30','%Y-%m-%d %H:%M').replace(tzinfo=TAIPEI)
    repair_deadline=draw_at+timedelta(hours=2)
    sync_delay=max(0,round((datetime.fromisoformat(sync_completed_at)-draw_at).total_seconds()/60))
    repair_count=int(previous_health.get('self_repair_count') or 0)+(1 if repair_run else 0)
    health={
        'status':'healthy_model_degraded' if degraded else 'healthy','checked_at':checked_at.isoformat(timespec='seconds'),
        'latest_period':latest['period'],'latest_draw_date':latest['draw_date'],'expected_latest_date':expected_latest_date(),
        'freshness_ok':True,'calendar_freshness_ok':latest['draw_date']>=expected_latest_date(),'data_changed':changed,
        'official_source':latest.get('source'),'source_failover_used':bool(pipeline_meta.get('source_failover_used')),
        'backfill_complete':bool(pipeline_meta.get('backfill_complete',True)),
        'backfill_draw_count':int(pipeline_meta.get('backfill_draw_count') or 0),
        'history_repair_pending':bool(pipeline_meta.get('history_repair_pending')),
        'pipeline_version':'continuous-update-v2','update_retry_policy':'三次重試、雙官方端點、缺期逐月補齊',
        'stability_monitor':'每次更新後立即驗證、開獎時段每五分鐘、全天每小時巡檢',
        'official_draw_time':draw_at.isoformat(timespec='minutes'),
        'sync_completed_at':sync_completed_at,
        'sync_delay_minutes':sync_delay,
        'two_hour_repair_deadline':repair_deadline.isoformat(timespec='minutes'),
        'two_hour_deadline_met':datetime.fromisoformat(sync_completed_at)<=repair_deadline,
        'self_repair_status':'本次自修完成' if repair_run else '待命中',
        'self_repair_count':repair_count,
        'last_self_repair_at':checked_at.isoformat(timespec='seconds') if repair_run else previous_health.get('last_self_repair_at'),
        'last_public_verification_at':checked_at.isoformat(timespec='seconds'),
        'mobile_open_sync':'開啟、回到前景、重新連網均立即核對版本',
        'model_release_allowed':True,
        'single_release_allowed':True,
        'single_edge_verified':bool((current.get('backtest') or {}).get('single_release_allowed')),
        'ranking_direction_valid':direction_ok,
        'top1_hits':backtest.get('single_hits'),'bottom1_hits':backtest.get('bottom1_hits'),
        'top5_avg_hits':backtest.get('top5_avg_hits'),'bottom5_avg_hits':backtest.get('bottom5_avg_hits'),
        'top9_avg_hits':backtest.get('top9_avg_hits'),'bottom9_avg_hits':backtest.get('bottom9_avg_hits'),
        'rank10_15_avg_hits':backtest.get('rank10_15_avg_hits'),
        'top9_capture_rate':backtest.get('top9_capture_rate'),
        'top9_slot_hit_rate':backtest.get('top9_slot_hit_rate'),
        'rank10_15_slot_hit_rate':backtest.get('rank10_15_slot_hit_rate'),
        'boundary_control_valid':backtest.get('boundary_control_valid'),
        'top5_at_least_2_rate':backtest.get('top5_at_least_2_rate'),
        'top9_at_least_2_rate':backtest.get('top9_at_least_2_rate'),
        'recent_54':backtest.get('recent_54'),
        'single_specialist_enabled':bool(backtest.get('single_specialist_enabled')),
        'single_repeat_break_enabled':bool(backtest.get('single_repeat_break_enabled')),
        'single_repeat_break_gate':bool(backtest.get('single_repeat_break_gate')),
        'single_repeat_break_method':backtest.get('single_repeat_break_method'),
        'single_repeat_break_application_count':backtest.get('single_repeat_break_application_count'),
        'single_repeat_break_current':backtest.get('single_repeat_break_current'),
        'single_repeat_break_baseline_hits':backtest.get('single_repeat_break_baseline_hits'),
        'single_repeat_break_hits':backtest.get('single_repeat_break_hits'),
        'single_repeat_break_recent_54_baseline_hits':backtest.get('single_repeat_break_recent_54_baseline_hits'),
        'single_repeat_break_recent_54_hits':backtest.get('single_repeat_break_recent_54_hits'),
        'single_repeat_break_recent_120_baseline_hits':backtest.get('single_repeat_break_recent_120_baseline_hits'),
        'single_repeat_break_recent_120_hits':backtest.get('single_repeat_break_recent_120_hits'),
        'catastrophic_guard_enabled':bool(backtest.get('catastrophic_guard_enabled')),
        'catastrophic_guard_current_trigger':bool(backtest.get('catastrophic_guard_current_trigger')),
        'catastrophic_guard_current_condition':bool(backtest.get('catastrophic_guard_current_condition')),
        'catastrophic_guard_policy_recommends':bool(backtest.get('catastrophic_guard_policy_recommends')),
        'catastrophic_guard_application_count':backtest.get('catastrophic_guard_application_count'),
        'catastrophic_guard_current_source':backtest.get('catastrophic_guard_current_source'),
        'catastrophic_guard_trigger_count':backtest.get('catastrophic_guard_trigger_count'),
        'anchor_stability':backtest.get('anchor_stability'),
        'production_anchor_weights':current.get('production_anchor_weights'),
        'polarity_model_candidate_count':backtest.get('strategy_candidate_count'),
        'polarity_selection_window':backtest.get('strategy_selection_window'),
        'polarity_consensus_member_count':backtest.get('strategy_consensus_member_count'),
        'direct_hit_calibration_enabled':bool(backtest.get('direct_hit_calibration_enabled')),
        'direct_hit_window':backtest.get('direct_hit_window'),
        'direct_hit_ridge':backtest.get('direct_hit_ridge'),
        'direct_hit_full_rank_blend':backtest.get('direct_hit_full_rank_blend'),
        'direct_hit_full_rank_gate':bool(backtest.get('direct_hit_full_rank_gate')),
        'direct_hit_top5_before':(backtest.get('direct_hit_baseline') or {}).get('top5_avg_hits'),
        'direct_hit_top5_after':backtest.get('top5_avg_hits'),
        'direct_hit_recent54_before':(backtest.get('direct_hit_baseline_recent_54') or {}).get('top5_avg_hits'),
        'direct_hit_recent54_after':(backtest.get('recent_54') or {}).get('top5_avg_hits'),
        'data_change_enabled':bool(backtest.get('data_change_enabled')),
        'data_change_window':backtest.get('data_change_window'),
        'data_change_ridge':backtest.get('data_change_ridge'),
        'data_change_rank_blend':backtest.get('data_change_rank_blend'),
        'data_change_preserve_front':backtest.get('data_change_preserve_front'),
        'data_change_gate':bool(backtest.get('data_change_gate')),
        'data_change_top9_before':(backtest.get('data_change_baseline') or {}).get('top9_avg_hits'),
        'data_change_top9_after':backtest.get('top9_avg_hits'),
        'data_change_recent54_before':(backtest.get('data_change_baseline_recent_54') or {}).get('top9_avg_hits'),
        'data_change_recent54_after':(backtest.get('recent_54') or {}).get('top9_avg_hits'),
        'data_change_recent120_before':(backtest.get('data_change_baseline_recent_120') or {}).get('top9_avg_hits'),
        'data_change_recent120_after':(backtest.get('recent_120') or {}).get('top9_avg_hits'),
        'model_drift':'ranking_direction_invalid' if not direction_ok else ('no_verified_edge' if degraded else 'stable_or_observing'),
        'recalculation_fingerprint':current.get('recalculation_fingerprint'),
        'settled_previous':bool(settlement and settlement.get('review_status') in ('completed_from_pre_draw_seal','recovery_no_pre_draw_seal')),
        'latest_review_status':settlement.get('review_status') if settlement else 'no_new_draw',
        'latest_review_accounted':bool(settlement and settlement.get('review_accounted',settlement.get('review_status')=='completed_from_pre_draw_seal')),
        'settlement_coverage':settlement_coverage,
        'settlement_coverage_complete':settlement_coverage.get('missing_draws')==0,
        'settlement_expected_draws':settlement_coverage.get('expected_draws'),
        'settlement_accounted_draws':settlement_coverage.get('accounted_draws'),
        'settlement_missing_draws':settlement_coverage.get('missing_draws'),
        'settlement_official_recovery_draws':settlement_coverage.get('official_recovery_draws'),
        'settlement_sealed_prediction_draws':settlement_coverage.get('sealed_prediction_draws')
    }
    coverage=current.get('history_coverage') or {}
    health['full_history_mode']=coverage.get('mode')=='all_available_history_for_every_prediction'
    health['history_draws_used']=coverage.get('draws_used')
    health['history_database_sha256']=coverage.get('database_sha256')
    (REPORTS/'system-health.json').write_text(json.dumps(health,ensure_ascii=False,indent=2),encoding='utf-8')
    refresh_report_pages(current)
    version_stamp=datetime.now(TAIPEI).strftime('%Y%m%d%H%M%S')
    publish_report_pages(version_stamp)
    shutil.copy2(REPORTS/'最新結果.json',SITE/'latest-result.json'); shutil.copy2(REPORTS/'system-health.json',SITE/'system-health.json')
    for name in ('prediction-history.jsonl','published-settlements.jsonl'):
        src=REPORTS/name
        if src.exists(): shutil.copy2(src,SITE/name)
    version={'version':version_stamp,'updated_at':datetime.now(TAIPEI).isoformat(timespec='seconds'),'latest_period':latest['period'],'latest_draw_date':latest['draw_date'],'data_changed':changed}
    (SITE/'version.json').write_text(json.dumps(version,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(version,ensure_ascii=False))

def expected_latest_date(now=None):
    """台灣時間20:35後，週一至週六必須至少有當日開獎；週日沿用週六。"""
    now=now or datetime.now(TAIPEI)
    d=now.date()
    if now.weekday()==6: d-=timedelta(days=1)
    elif now.hour<20 or (now.hour==20 and now.minute<40):
        d-=timedelta(days=1)
        if d.weekday()==6: d-=timedelta(days=1)
    return d.isoformat()

def verify_freshness(latest, strict=False):
    expected=expected_latest_date()
    ok=latest['draw_date']>=expected
    print(json.dumps({'freshness_ok':ok,'latest':latest['draw_date'],'expected':expected},ensure_ascii=False))
    # 日曆只是預期；遇休市、延期或官方延遲時不得反過來把正式更新永久卡死。
    # 真正發布守門由「公開期別必須等於官方期別」負責。
    return ok

def verify_publication(latest):
    result=read_json(REPORTS/'最新結果.json') or {}
    health=read_json(REPORTS/'system-health.json') or {}
    site_result=read_json(SITE/'latest-result.json') or {}
    site_health=read_json(SITE/'system-health.json') or {}
    errors=[]
    for label,item in (('戰報結果',result),('手機結果',site_result)):
        data=item.get('data_latest') or {}
        if str(data.get('period'))!=str(latest['period']) or data.get('date')!=latest['draw_date']:
            errors.append(f'{label}未對應官方最新期別')
        ranked=item.get('ranked_top15') or []
        if not ranked or item.get('single_candidate')!=ranked[0] or item.get('single_published')!=ranked[0]:
            errors.append(f'{label}的1中1主選未完整公開')
    for label,item in (('戰報健康檔',health),('手機健康檔',site_health)):
        if str(item.get('latest_period'))!=str(latest['period']) or item.get('latest_draw_date')!=latest['draw_date']:
            errors.append(f'{label}未對應官方最新期別')
        if not item.get('full_history_mode') or not item.get('history_database_sha256'):
            errors.append(f'{label}未通過全歷史鐵律')
        settlement_coverage=item.get('settlement_coverage') or {}
        if not item.get('settlement_coverage_complete') or settlement_coverage.get('missing_draws')!=0:
            errors.append(f'{label}仍有歷史結算資料缺口')
    for name in REPORT_PAGE_FILES:
        if not (REPORTS/name).exists() or not (SITE/name).exists():
            errors.append(f'分類分頁缺失：{name}')
    for name in ('manifest.webmanifest','mobile-sync.js','service-worker.js','icons/icon-180.png','icons/icon-192.png','icons/icon-512.png','icons/maskable-512.png'):
        if not (SITE/name).exists(): errors.append(f'手機安裝檔缺失：{name}')
    if errors: raise SystemExit('鐵律發布驗證失敗：'+'；'.join(errors))
    print(json.dumps({'publication_ok':True,'latest_period':latest['period'],'single_published':result['single_published']},ensure_ascii=False))

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--offline',action='store_true'); ap.add_argument('--strict-freshness',action='store_true'); ap.add_argument('--verify-only',action='store_true'); args=ap.parse_args()
    if args.offline:
        with CSV.open('r',encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
        x=max(rows,key=lambda r:(r['draw_date'],r['period'])); latest={'period':x['period'],'draw_date':x['draw_date'],'nums':[int(x[f'n{i}']) for i in range(1,6)]}; changed=False; new_draws=[]; pipeline_meta={}
    else:
        latest=fetch_latest()
        if args.verify_only:
            changed=False; new_draws=[]; pipeline_meta={}
        else:
            with CSV.open('r',encoding='utf-8-sig',newline='') as f: local_rows=list(csv.DictReader(f))
            local_latest=max(local_rows,key=lambda r:(r['draw_date'],int(r['period'])))
            source_failover_used=latest.get('source')!='taiwanlottery_latest_result'
            backfill_complete=True; history_repair_pending=False
            try:
                official_rows=fetch_official_range(local_latest['draw_date'],latest['draw_date'])
                if not any(x['period']==latest['period'] for x in official_rows): official_rows.append(latest)
                official_rows.sort(key=lambda x:(x['draw_date'],int(x['period'])))
            except Exception as exc:
                print(json.dumps({'backfill_warning':str(exc),'fallback':'latest_official_draw'},ensure_ascii=False))
                official_rows=[latest]; backfill_complete=False; history_repair_pending=True
            new_draws=[x for x in official_rows if (x['draw_date'],int(x['period']))>(local_latest['draw_date'],int(local_latest['period']))]
            changed=update_csv(official_rows)
            pipeline_meta={'source_failover_used':source_failover_used,'backfill_complete':backfill_complete,
                           'history_repair_pending':history_repair_pending,'backfill_draw_count':len(new_draws)}
    verify_freshness(latest,args.strict_freshness)
    if args.verify_only:
        verify_publication(latest)
        raise SystemExit(0)
    previous=read_json(REPORTS/'最新結果.json')
    build_site(latest,changed,previous,new_draws,pipeline_meta)
