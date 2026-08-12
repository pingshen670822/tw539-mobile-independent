#!/usr/bin/env python3
"""防止一般修改意外破壞自動更新鐵律。"""
import argparse
import html
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
checks={
    ROOT/'.github/workflows/auto-update.yml':['push:','branches: [master]','report_pages.py','--strict-freshness','--structure-only','鐵律最終驗證','ironlaw_guard.py','issues: write','for attempt in 1 2 3','git fetch origin master','git rebase origin/master','actions/checkout@v7','actions/setup-python@v7','actions/configure-pages@v6','actions/upload-pages-artifact@v5','actions/deploy-pages@v5'],
    ROOT/'cloud_pipeline.py':['verify_freshness','verify_publication','expected_latest_date','prediction-history.jsonl','published-settlements.jsonl','compact_prediction_history','enrich_settlement','completed_from_pre_draw_seal','no_post_draw_substitution','rolling_adjustment','rank10_15_hits','boundary_review_status','boundary_discrimination_gap','polarity_model_candidate_count','polarity_selection_window','polarity_consensus_member_count','full_history_mode','replace=True','ranking_direction_valid','datetime.now(TAIPEI)','REPORT_PAGE_FILES','refresh_report_pages','two_hour_repair_deadline','self_repair_count','mobile_open_sync','apple-touch-icon','mobile-web-app-capable','icons/icon-180.png','icons/icon-192.png','icons/icon-512.png','icons/maskable-512.png'],
    ROOT/'tw539_ultra.py':['FORMAL_FEATURE_KEYS','GLOBAL_HISTORY_BLEND = 1.00','MODEL_SEARCH_CANDIDATE_COUNT = 286','MAX_ANCHOR_MODULE_WEIGHT = .50','ROLLING_ENSEMBLE_MEMBERS = 3','MIN_ENSEMBLE_WEIGHT_DISTANCE = .60','POLARITY_SELECTION_WINDOW = 360','POLARITY_CONSENSUS_MEMBERS = 5','SINGLE_SPECIALIST_WINDOW = 30','CATASTROPHIC_TOP9_HIT_LIMIT = 0','CATASTROPHIC_AVG_RANK_FLOOR = 22.0','CATASTROPHIC_ROTATION = 12','STABILITY_CHAMPION_ANCHOR','anchor_challenger_wins','production_anchor_weights','apply_catastrophic_guard','catastrophic_guard_current_trigger','single_specialist_enabled','single_specialist_lift','single_strong_conditions','ROLLING_BOUNDARY_BLEND_CANDIDATES','select_rolling_weights','adaptive_polarity_backtest','rolling_weight_update','thirty_polarity_models_360_draw_five_member_weight_consensus','三十組方向模型逐期競賽','strategy_consensus_member_count','每期開獎命中檢討與滾動修正','錯誤模組與前9邊界逐項檢討','前9邊界偏移','禁止開獎後換號或補號','FEATURE_LABELS','短期視窗不得參與正式排名','all_available_history_for_every_prediction','history_coverage','"single_published": ranked[0]','bottom1_hits','bottom5_avg_hits','rank10_15_avg_hits','top9_capture_rate','top9_slot_hit_rate','rank10_15_slot_hit_rate','boundary_control_valid','ranking_direction_valid','model_selection_cutoff','強制投注排除名單','禁止進入任何推薦牌組','full_history_scan','model_score_with_repeat_qualification','連莊資格驗算','相對指數至少75','全歷史連莊率不低於12.82%','repeat_backtest_pass','不做補位','def rank_numbers','公平破同分','render_report_pages'],
    ROOT/'report_pages.py':['PAGE_NAMES','本期最強1顆','最強號碼多邏輯總結','強烈推薦守門','本期分級主選','2中1～2','3中1～3','5中2～3','9中3～5','最後360期隔離回測','最新一期命中結算','開獎前前5正式預測','前5命中資料','開獎前封存實戰紀錄','正式方向模型','全系統重組','五組正式權重共識','鐵律守門','開獎後更新與自主修復','安裝手機版','加入主畫面','def render_report_pages'],
    ROOT/'system_audit.py':['整套系統驗收失敗','1中1主選未固定產出並公開','戰報可見英文','正式主選與隔離回測不是同一組權重','最新開獎錯誤沒有觸發三十組方向模型五組權重共識','命中檢討','三十組前9邊界參數','推薦牌組含強制投注排除號碼'],
    ROOT/'site/manifest.webmanifest':['"id": "./"','"scope": "./"','"display": "standalone"','icon-192.png','icon-512.png','maskable-512.png'],
    ROOT/'site/service-worker.js':["cache:'no-store'",'tw539-mobile-ironlaw-v6','system-health.json','backtest.html','review.html','history.html','models.html','health.html','mobile-sync.js','icons/icon-192.png','icons/icon-512.png','icons/maskable-512.png'],
    ROOT/'site/mobile-sync.js':['setTimeout(checkVersion,30000)','setTimeout(checkVersion,5000)','visibilitychange','pageshow','online','同步正常','同步重試中','beforeinstallprompt','appinstalled','install-app-button','手機版已安裝'],
    ROOT/'.github/workflows/watchdog.yml':['watchdog.py','auto-update.yml','repair=true','30,35,40,45,50,55 12','*/5 13-16','actions: write','actions/checkout@v7','actions/setup-python@v7'],
    ROOT/'watchdog.py':['system-health.json','published-settlements.jsonl','full_history_mode','latest_period','開獎後兩小時官方資料仍未取得','自主修復欄位','三十組方向模型、三百六十期選擇窗與五組權重共識','第10至15名偏移檢查','REPORT_PAGES','本期預測頁混入其他分類資料','開獎檢討分頁內容不完整'],
}
checks[ROOT/'tw539_ultra.py'].append('CATASTROPHIC_GUARD_EXECUTION_ENABLED = False')
checks[ROOT/'tw539_ultra.py'].remove('thirty_polarity_models_360_draw_five_member_weight_consensus')
checks[ROOT/'tw539_ultra.py'].extend(['DIRECT_HIT_WINDOW = 360','DIRECT_HIT_RIDGE = 10.0',
                                     'DIRECT_HIT_FULL_RANK_BLEND = .15','direct_hit_prefix',
                                     'blend_direct_full_ranking','direct_hit_full_rank_gate',
                                     'DATA_CHANGE_WINDOW = 720','DATA_CHANGE_RIDGE = 1.0',
                                     'DATA_CHANGE_RANK_BLEND = .50','DATA_CHANGE_PRESERVE_FRONT = 5',
                                     'data_change_cases','blend_data_change_ranking','data_change_gate',
                                     'SINGLE_REPEAT_BREAK_COOLDOWN = 1','apply_single_repeat_break',
                                     'single_repeat_break_gate',
                                     'five_member_consensus_with_direct_hit_single_repeat_and_data_change_front9'])
checks[ROOT/'report_pages.py'].extend(['直接命中全排序校準','前9集合允許修正','單碼重複冷卻','每期資料變化校正'])
checks[ROOT/'system_audit.py'].remove('最新開獎錯誤沒有觸發三十組方向模型五組權重共識')
checks[ROOT/'system_audit.py'].append('最新開獎錯誤沒有觸發五組方向共識、直接命中、單碼冷卻與資料變化校正')
checks[ROOT/'watchdog.py'].remove('三十組方向模型、三百六十期選擇窗與五組權重共識')
checks[ROOT/'watchdog.py'].extend(['五組方向共識、直接命中、單碼冷卻與資料變化校正','直接命中全排序校準','單碼重複冷卻'])
checks[ROOT/'watchdog.py'].append('每期資料變化校正')
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
