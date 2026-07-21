#!/usr/bin/env python3
"""防止一般修改意外破壞自動更新鐵律。"""
import argparse
import html
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
checks={
    ROOT/'.github/workflows/auto-update.yml':['--strict-freshness','--structure-only','鐵律最終驗證','ironlaw_guard.py','issues: write','actions/checkout@v7','actions/setup-python@v7','actions/configure-pages@v6','actions/upload-pages-artifact@v5','actions/deploy-pages@v5'],
    ROOT/'cloud_pipeline.py':['verify_freshness','verify_publication','expected_latest_date','prediction-history.jsonl','published-settlements.jsonl','full_history_mode','replace=True'],
    ROOT/'tw539_ultra.py':['GLOBAL_HISTORY_WEIGHTS','GLOBAL_HISTORY_BLEND = 1.00','FEATURE_LABELS','全歷史共現關聯','短期視窗不得參與正式排名','all_available_history_for_every_prediction','history_coverage','"single_published": ranked[0]'],
    ROOT/'system_audit.py':['整套系統驗收失敗','1中1主選未固定產出並公開','戰報可見英文'],
    ROOT/'site/service-worker.js':["cache:'no-store'",'tw539-mobile-ironlaw-v3','system-health.json'],
    ROOT/'site/mobile-sync.js':['setInterval(checkVersion,30000)','同步正常','網路中斷，顯示最近資料'],
    ROOT/'.github/workflows/watchdog.yml':['watchdog.py','auto-update.yml','actions: write','actions/checkout@v7','actions/setup-python@v7'],
    ROOT/'watchdog.py':['system-health.json','full_history_mode','latest_period','戰報可見文字含英文'],
}
parser=argparse.ArgumentParser()
parser.add_argument('--structure-only',action='store_true')
args=parser.parse_args()
bad=[]
for path,terms in checks.items():
    text=path.read_text(encoding='utf-8') if path.exists() else ''
    for term in terms:
        if term not in text: bad.append(f'{path.name} 缺少 {term}')
if not args.structure_only:
    report=ROOT/'reports/最新539科學預測戰報.html'
    if not report.exists():
        bad.append('缺少最新戰報')
    else:
        page=report.read_text(encoding='utf-8')
        visible=re.sub(r'(?is)<(?:style|script)\b[^>]*>.*?</(?:style|script)>',' ',page)
        visible=html.unescape(re.sub(r'(?s)<[^>]+>',' ',visible))
        english=sorted(set(re.findall(r'[A-Za-z][A-Za-z0-9_-]*',visible)))
        if english: bad.append('戰報可見文字含英文：'+','.join(english))
if bad: raise SystemExit('鐵律完整性失敗：'+'；'.join(bad))
print('鐵律完整性檢查通過')
