#!/usr/bin/env python3
"""防止一般修改意外破壞自動更新鐵律。"""
import argparse
import html
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
checks={
    ROOT/'.github/workflows/auto-update.yml':['push:','branches: [master]','report_pages.py','--strict-freshness','--structure-only','鐵律最終驗證','ironlaw_guard.py','issues: write','actions/checkout@v7','actions/setup-python@v7','actions/configure-pages@v6','actions/upload-pages-artifact@v5','actions/deploy-pages@v5'],
    ROOT/'cloud_pipeline.py':['verify_freshness','verify_publication','expected_latest_date','prediction-history.jsonl','published-settlements.jsonl','compact_prediction_history','enrich_settlement','completed_from_pre_draw_seal','no_post_draw_substitution','rolling_adjustment','rank10_15_hits','boundary_review_status','boundary_discrimination_gap','polarity_model_candidate_count','polarity_selection_window','full_history_mode','replace=True','ranking_direction_valid','datetime.now(TAIPEI)','REPORT_PAGE_FILES','refresh_report_pages'],
    ROOT/'tw539_ultra.py':['FORMAL_FEATURE_KEYS','GLOBAL_HISTORY_BLEND = 1.00','MODEL_SEARCH_CANDIDATE_COUNT = 286','MAX_ANCHOR_MODULE_WEIGHT = .50','ROLLING_ENSEMBLE_MEMBERS = 3','MIN_ENSEMBLE_WEIGHT_DISTANCE = .60','POLARITY_SELECTION_WINDOW = 90','ROLLING_BOUNDARY_BLEND_CANDIDATES','select_rolling_weights','adaptive_polarity_backtest','rolling_weight_update','thirty_polarity_models_ninety_draw_walk_forward_selection','三十組模組正反方向逐期競賽','每期開獎命中檢討與滾動修正','錯誤模組與前9邊界逐項檢討','前9邊界偏移','禁止開獎後換號或補號','FEATURE_LABELS','短期視窗不得參與正式排名','all_available_history_for_every_prediction','history_coverage','"single_published": ranked[0]','bottom1_hits','bottom5_avg_hits','rank10_15_avg_hits','top9_capture_rate','top9_slot_hit_rate','rank10_15_slot_hit_rate','boundary_control_valid','ranking_direction_valid','model_selection_cutoff','三十組方向模型每期只讀當時以前資料','強制投注排除名單','禁止進入任何推薦牌組','full_history_scan','model_score_with_repeat_qualification','連莊資格驗算','相對指數至少75','全歷史連莊率不低於12.82%','repeat_backtest_pass','不做補位','def rank_numbers','公平破同分','render_report_pages'],
    ROOT/'report_pages.py':['PAGE_NAMES','本期分級主選','2中1～2','3中1～3','5中2～3','9中3～5','最後360期隔離回測','最新一期命中結算','開獎前封存實戰紀錄','正式方向模型','鐵律守門','def render_report_pages'],
    ROOT/'system_audit.py':['整套系統驗收失敗','1中1主選未固定產出並公開','戰報可見英文','正式主選與隔離回測不是同一組權重','最新開獎錯誤沒有觸發三十組方向模型逐期重選','命中檢討','三十組前9邊界參數','推薦牌組含強制投注排除號碼'],
    ROOT/'site/service-worker.js':["cache:'no-store'",'tw539-mobile-ironlaw-v4','system-health.json','backtest.html','review.html','history.html','models.html','health.html'],
    ROOT/'site/mobile-sync.js':['setInterval(checkVersion,30000)','同步正常','網路中斷，顯示最近資料'],
    ROOT/'.github/workflows/watchdog.yml':['watchdog.py','auto-update.yml','actions: write','actions/checkout@v7','actions/setup-python@v7'],
    ROOT/'watchdog.py':['system-health.json','published-settlements.jsonl','full_history_mode','latest_period','最新開獎錯誤沒有觸發三十組方向模型與九十期逐期重選','第10至15名偏移檢查','REPORT_PAGES','本期預測頁混入其他分類資料','開獎檢討分頁內容不完整'],
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
    pages=('index.html','backtest.html','review.html','history.html','models.html','health.html')
    for name in pages:
        report=ROOT/'reports'/name
        if not report.exists():
            bad.append(f'缺少戰報分頁 {name}')
            continue
        page=report.read_text(encoding='utf-8')
        visible=re.sub(r'(?is)<(?:style|script)\b[^>]*>.*?</(?:style|script)>',' ',page)
        visible=html.unescape(re.sub(r'(?s)<[^>]+>',' ',visible))
        english=sorted(set(re.findall(r'[A-Za-z][A-Za-z0-9_-]*',visible)))
        if english: bad.append(f'{name} 可見文字含英文：'+','.join(english))
if bad: raise SystemExit('鐵律完整性失敗：'+'；'.join(bad))
print('鐵律完整性檢查通過')
