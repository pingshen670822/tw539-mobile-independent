#!/usr/bin/env python3
"""官方最新開獎 -> 驗證 -> 重算 -> 產生獨立 PWA。僅使用 Python 標準庫。"""
from __future__ import annotations
import argparse, csv, json, shutil, subprocess, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent; CSV=ROOT/'data'/'539.csv'; SITE=ROOT/'site'; REPORTS=ROOT/'reports'; REPORT=REPORTS/'最新539科學預測戰報.html'
API='https://api.taiwanlottery.com/TLCAPIWeB/Lottery/LatestResult'
TAIPEI=timezone(timedelta(hours=8))

def fetch_latest():
    last=None
    for delay in (0,3,10):
        if delay: time.sleep(delay)
        try:
            req=urllib.request.Request(API,headers={'User-Agent':'Mozilla/5.0 TW539-cloud/1.0','Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=40) as r: payload=json.load(r)
            x=(payload.get('content') or {}).get('daily539Result')
            nums=[int(n) for n in x['drawNumberSize'][:5]]
            raw=str(x['lotteryDate']).split('T')[0].replace('/','-')
            if len(set(nums))!=5 or any(n<1 or n>39 for n in nums): raise ValueError('官方號碼驗證失敗')
            return {'period':str(x['period']),'draw_date':raw,'nums':sorted(nums),'order':x.get('drawNumberAppear',[])[:5]}
        except Exception as e: last=e
    raise RuntimeError(f'官方最新開獎取得失敗：{last}')

def update_csv(latest):
    with CSV.open('r',encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f)); fields=list(rows[0])
    current=max(rows,key=lambda r:(r['draw_date'],r['period']))
    existing=next((r for r in rows if r['period']==latest['period']),None)
    if existing:
        old_nums=sorted(int(existing[f'n{i}']) for i in range(1,6))
        if existing['draw_date']==latest['draw_date'] and old_nums==latest['nums']: return False
        row=existing
        rows.remove(existing)
    elif (latest['draw_date'],latest['period']) <= (current['draw_date'],current['period']):
        return False
    else:
        row={k:'' for k in fields}
    row.update({'period':latest['period'],'draw_date':latest['draw_date'],'draw_order':','.join(f'{int(n):02}' for n in latest['order']),'source':'taiwanlottery_latest_result','fetched_at':datetime.now().isoformat(timespec='seconds')})
    for i,n in enumerate(latest['nums'],1): row[f'n{i}']=str(n)
    rows.append(row); rows.sort(key=lambda r:(r['draw_date'],r['period']))
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
    for index,existing in enumerate(old):
        if unique_key(existing)==unique_key(item):
            if not replace: return False
            old[index]=item
            path.write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in old)+'\n',encoding='utf-8')
            return True
    old.append(item)
    path.write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in old)+'\n',encoding='utf-8')
    return True

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
        'settled_at':datetime.now().astimezone().isoformat(timespec='seconds')
    }
    append_jsonl(REPORTS/'published-settlements.jsonl',item,lambda x:(x.get('target_draw_date'),x.get('fingerprint')))
    return item

def build_site(latest, changed, previous=None):
    settlement=settle_previous(previous,latest)
    subprocess.run([sys.executable,str(ROOT/'tw539_ultra.py'),'--backtest','360'],check=True,cwd=ROOT)
    current=read_json(REPORTS/'最新結果.json') or {}
    append_jsonl(REPORTS/'prediction-history.jsonl',current,lambda x:(x.get('target_draw_date'),x.get('recalculation_fingerprint')),replace=True)
    backtest=current.get('backtest') or {}
    direction_ok=bool(backtest.get('ranking_direction_valid'))
    degraded=(not direction_ok) or (backtest.get('single_rate',0)<=backtest.get('single_random_baseline',0) and backtest.get('top9_avg_hits',0)<=backtest.get('top9_random_baseline',0))
    health={
        'status':'healthy_model_degraded' if degraded else 'healthy','checked_at':datetime.now().astimezone().isoformat(timespec='seconds'),
        'latest_period':latest['period'],'latest_draw_date':latest['draw_date'],'expected_latest_date':expected_latest_date(),
        'freshness_ok':latest['draw_date']>=expected_latest_date(),'data_changed':changed,
        'model_release_allowed':True,
        'single_release_allowed':True,
        'single_edge_verified':bool((current.get('backtest') or {}).get('single_release_allowed')),
        'ranking_direction_valid':direction_ok,
        'top1_hits':backtest.get('single_hits'),'bottom1_hits':backtest.get('bottom1_hits'),
        'top5_avg_hits':backtest.get('top5_avg_hits'),'bottom5_avg_hits':backtest.get('bottom5_avg_hits'),
        'top9_avg_hits':backtest.get('top9_avg_hits'),'bottom9_avg_hits':backtest.get('bottom9_avg_hits'),
        'model_drift':'ranking_direction_invalid' if not direction_ok else ('no_verified_edge' if degraded else 'stable_or_observing'),
        'recalculation_fingerprint':current.get('recalculation_fingerprint'),'settled_previous':settlement is not None
    }
    coverage=current.get('history_coverage') or {}
    health['full_history_mode']=coverage.get('mode')=='all_available_history_for_every_prediction'
    health['history_draws_used']=coverage.get('draws_used')
    health['history_database_sha256']=coverage.get('database_sha256')
    (REPORTS/'system-health.json').write_text(json.dumps(health,ensure_ascii=False,indent=2),encoding='utf-8')
    SITE.mkdir(exist_ok=True); shutil.copy2(REPORT,SITE/'index.html'); shutil.copy2(REPORTS/'最新結果.json',SITE/'latest-result.json'); shutil.copy2(REPORTS/'system-health.json',SITE/'system-health.json')
    for name in ('prediction-history.jsonl','published-settlements.jsonl'):
        src=REPORTS/name
        if src.exists(): shutil.copy2(src,SITE/name)
    page=(SITE/'index.html').read_text(encoding='utf-8')
    page=page.replace("<title>","<link rel='manifest' href='./manifest.webmanifest'><meta name='theme-color' content='#8b0000'><title>",1)
    page=page.replace('</body>',"<script src='./mobile-sync.js'></script></body>") if '</body>' in page else page.replace('</html>',"<script src='./mobile-sync.js'></script></html>")
    (SITE/'index.html').write_text(page,encoding='utf-8')
    version={'version':datetime.now().strftime('%Y%m%d%H%M%S'),'updated_at':datetime.now().astimezone().isoformat(timespec='seconds'),'latest_period':latest['period'],'latest_draw_date':latest['draw_date'],'data_changed':changed}
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
    if strict and not ok: raise SystemExit(f'鐵律失敗：資料過期，最新 {latest["draw_date"]}，至少應為 {expected}')
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
    if errors: raise SystemExit('鐵律發布驗證失敗：'+'；'.join(errors))
    print(json.dumps({'publication_ok':True,'latest_period':latest['period'],'single_published':result['single_published']},ensure_ascii=False))

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--offline',action='store_true'); ap.add_argument('--strict-freshness',action='store_true'); ap.add_argument('--verify-only',action='store_true'); args=ap.parse_args()
    if args.offline:
        with CSV.open('r',encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
        x=max(rows,key=lambda r:(r['draw_date'],r['period'])); latest={'period':x['period'],'draw_date':x['draw_date'],'nums':[int(x[f'n{i}']) for i in range(1,6)]}; changed=False
    else:
        latest=fetch_latest()
        changed=False if args.verify_only else update_csv(latest)
    verify_freshness(latest,args.strict_freshness)
    if args.verify_only:
        verify_publication(latest)
        raise SystemExit(0)
    previous=read_json(REPORTS/'最新結果.json')
    build_site(latest,changed,previous)
