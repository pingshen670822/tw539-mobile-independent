#!/usr/bin/env python3
"""官方最新開獎 -> 驗證 -> 重算 -> 產生獨立 PWA。僅使用 Python 標準庫。"""
from __future__ import annotations
import argparse, csv, json, shutil, subprocess, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent; CSV=ROOT/'data'/'539.csv'; SITE=ROOT/'site'; REPORT=ROOT/'reports'/'最新539科學預測戰報.html'
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
    if (latest['draw_date'],latest['period']) <= (current['draw_date'],current['period']): return False
    row={k:'' for k in fields}; row.update({'period':latest['period'],'draw_date':latest['draw_date'],'draw_order':','.join(f'{n:02}' for n in latest['order']),'source':'taiwanlottery_latest_result','fetched_at':datetime.now().isoformat(timespec='seconds')})
    for i,n in enumerate(latest['nums'],1): row[f'n{i}']=str(n)
    rows.append(row); rows.sort(key=lambda r:(r['draw_date'],r['period']))
    tmp=CSV.with_suffix('.csv.tmp')
    with tmp.open('w',encoding='utf-8-sig',newline='') as f: w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    tmp.replace(CSV); return True

def build_site(latest, changed):
    subprocess.run([sys.executable,str(ROOT/'tw539_ultra.py'),'--backtest','360'],check=True,cwd=ROOT)
    SITE.mkdir(exist_ok=True); shutil.copy2(REPORT,SITE/'index.html'); shutil.copy2(ROOT/'reports'/'最新結果.json',SITE/'latest-result.json')
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
    elif now.hour<20 or (now.hour==20 and now.minute<35):
        d-=timedelta(days=1)
        if d.weekday()==6: d-=timedelta(days=1)
    return d.isoformat()

def verify_freshness(latest, strict=False):
    expected=expected_latest_date()
    ok=latest['draw_date']>=expected
    print(json.dumps({'freshness_ok':ok,'latest':latest['draw_date'],'expected':expected},ensure_ascii=False))
    if strict and not ok: raise SystemExit(f'鐵律失敗：資料過期，最新 {latest["draw_date"]}，至少應為 {expected}')
    return ok

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--offline',action='store_true'); ap.add_argument('--strict-freshness',action='store_true'); ap.add_argument('--verify-only',action='store_true'); args=ap.parse_args()
    if args.offline:
        with CSV.open('r',encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
        x=max(rows,key=lambda r:(r['draw_date'],r['period'])); latest={'period':x['period'],'draw_date':x['draw_date'],'nums':[int(x[f'n{i}']) for i in range(1,6)]}; changed=False
    else: latest=fetch_latest(); changed=update_csv(latest)
    verify_freshness(latest,args.strict_freshness)
    if not args.verify_only: build_site(latest,changed)
