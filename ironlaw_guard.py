#!/usr/bin/env python3
"""防止一般修改意外破壞自動更新鐵律。"""
from pathlib import Path

ROOT=Path(__file__).resolve().parent
checks={
    ROOT/'.github/workflows/auto-update.yml':['--strict-freshness','鐵律最終驗證','ironlaw_guard.py','issues: write'],
    ROOT/'cloud_pipeline.py':['verify_freshness','expected_latest_date','prediction-history.jsonl','published-settlements.jsonl','full_history_mode'],
    ROOT/'tw539_ultra.py':['GLOBAL_HISTORY_WEIGHTS','GLOBAL_HISTORY_BLEND = .60','all_available_history_for_every_prediction','history_coverage'],
    ROOT/'site/service-worker.js':["cache:'no-store'",'tw539-mobile-ironlaw-v2'],
    ROOT/'site/mobile-sync.js':['setInterval(checkVersion,30000)'],
}
bad=[]
for path,terms in checks.items():
    text=path.read_text(encoding='utf-8') if path.exists() else ''
    for term in terms:
        if term not in text: bad.append(f'{path.name} 缺少 {term}')
if bad: raise SystemExit('鐵律完整性失敗：'+'；'.join(bad))
print('鐵律完整性檢查通過')
