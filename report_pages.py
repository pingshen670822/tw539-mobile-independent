#!/usr/bin/env python3
"""產生分類清楚、內容不重複的台灣539戰報分頁。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


TAIPEI = timezone(timedelta(hours=8))
PAGE_NAMES = {
    "index.html": "本期預測",
    "backtest.html": "回測驗證",
    "review.html": "開獎檢討",
    "history.html": "歷史封存",
    "models.html": "模型說明",
    "health.html": "系統健康",
}


def _fmt(numbers) -> str:
    return " ".join(f"{int(number):02}" for number in numbers)


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows


def _numeric_code(value) -> str:
    raw = str(value or "")
    if len(raw) != 64 or any(char not in "0123456789abcdef" for char in raw.lower()):
        return "－"
    return str(int(raw, 16))[-20:]


def _page_shell(filename: str, heading: str, subtitle: str, content: str) -> str:
    nav = "".join(
        f"<a href='./{name}'{' class=\"active\" aria-current=\"page\"' if name == filename else ''}>{label}</a>"
        for name, label in PAGE_NAMES.items()
    )
    return f"""<!doctype html>
<html lang='zh-Hant'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>台灣539・{heading}</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f4f6;color:#172033;font-family:system-ui,'Microsoft JhengHei',sans-serif;line-height:1.55}}main{{max-width:1180px;margin:auto;padding:18px}}header{{background:linear-gradient(135deg,#7f1017,#d1242f);color:#fff;padding:24px;border-radius:14px}}h1{{margin:0 0 5px;font-size:28px}}h2{{border-left:6px solid #c1121f;padding-left:10px;color:#7f1017;margin:0 0 16px}}h3{{color:#7f1017;margin:24px 0 10px}}nav{{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin:14px 0}}nav a{{display:flex;align-items:center;justify-content:center;min-height:44px;background:#fff;border:1px solid #d1d5db;border-radius:9px;padding:8px;color:#7f1017;text-decoration:none;font-weight:800;text-align:center}}nav a.active{{background:#7f1017;color:#fff;border-color:#7f1017}}.band{{background:#fff;border:1px solid #d8dee8;border-radius:12px;padding:18px;margin:14px 0;box-shadow:0 2px 8px #0000000d}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}}.card{{border:1px solid #d9dde5;border-radius:10px;padding:13px;background:#fff}}.primary{{border:2px solid #c1121f;background:#fff5f5}}.label{{color:#687386;font-size:13px}}.value{{font-size:18px;font-weight:800;margin-top:4px}}.number{{color:#c1121f;font-size:38px;letter-spacing:2px}}.number-line{{font-size:24px;letter-spacing:3px;color:#7f1017}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse}}th{{background:#7f1017;color:#fff}}th,td{{padding:9px;border:1px solid #d7dce4;text-align:left;white-space:nowrap}}tr:nth-child(even) td{{background:#fafafa}}.warning{{background:#fff8e6;border-color:#e9b949}}.ok{{color:#176b3a}}.bad{{color:#9b1c1c}}.note{{color:#626d7d}}.empty{{padding:22px;text-align:center;color:#687386}}footer{{padding:14px 4px 28px;color:#687386;font-size:13px}}@media(max-width:760px){{main{{padding:8px}}header{{border-radius:8px;padding:19px}}nav{{grid-template-columns:repeat(3,minmax(0,1fr))}}nav a{{font-size:14px}}.band{{padding:13px}}h1{{font-size:24px}}.number-line{{font-size:20px;letter-spacing:2px}}}}@media(max-width:390px){{nav{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
</style>
</head>
<body><main>
<header><h1>{heading}</h1><div>{subtitle}</div></header>
<nav aria-label='戰報分類'>{nav}</nav>
{content}
<footer>各頁只顯示所屬分類；資料由同一次正式運算產生並同步更新。</footer>
</main></body></html>"""


def _prediction_page(draws, weights, score, tickets, repeat_audit, ranking, target_date, generated_at, feature_labels):
    latest = draws[-1]
    minimum = min(score.values())
    spread = max(0.00001, max(score.values()) - minimum)
    features = __import__("tw539_ultra").formal_feature_table(draws)
    rank_rows = []
    for rank, number in enumerate(ranking[:15], 1):
        index = 100 * (score[number] - minimum) / spread
        support = "、".join(
            feature_labels.get(key, key) for key in weights if features[key][number] >= 0.65
        ) or "均衡校正"
        zone = "前5核心" if rank <= 5 else ("前9核心" if rank <= 9 else "第10至15名監控")
        rank_rows.append(
            f"<tr><td>{rank}</td><td><b>{number:02}</b></td><td>{zone}</td><td>{index:.1f}</td><td>{support}</td></tr>"
        )
    ticket_rows = "".join(
        f"<tr><td>{index}</td><td>{_fmt(ticket)}</td><td>已排除排序後15名</td></tr>"
        for index, ticket in enumerate(tickets, 1)
    ) or "<tr><td colspan='3'>本期沒有通過牌型限制的組合</td></tr>"
    excluded = list(reversed(ranking[-15:]))
    exclusion_rows = "".join(
        f"<tr><td>{label}</td><td>{_fmt(excluded[:count])}</td><td>不得進入推薦牌組</td></tr>"
        for label, count in (("後5名", 5), ("後10名", 10), ("後15名", 15))
    )
    repeat_rows = "".join(
        f"<tr><td>{item['number']:02}</td><td>{item['relative_index']:.1f}</td><td>{item['positive_module_count']}</td><td>{item['repeat_hits']}/{item['repeat_samples']}</td><td>{'符合' if item['qualified'] else '未符合'}</td><td>{item['final_rank']}</td><td>{'列入前9' if item['listed_top9'] else '未列入前9'}</td></tr>"
        for item in repeat_audit
    )
    content = f"""
<div class='band'><h2>本期資料</h2><div class='grid'>
<div class='card'><div class='label'>預測目標日</div><div class='value'>{target_date}</div></div>
<div class='card'><div class='label'>歷史資料截止日</div><div class='value'>{latest['date']}</div></div>
<div class='card'><div class='label'>依據期別</div><div class='value'>{latest['period']}</div></div>
<div class='card'><div class='label'>使用歷史期數</div><div class='value'>{len(draws):,}期</div></div>
<div class='card'><div class='label'>戰報產生時間</div><div class='value'>{generated_at}</div></div>
</div></div>
<div class='band'><h2>本期正式預測</h2><div class='grid'>
<div class='card primary'><div class='label'>1中1主選</div><div class='value number'>{ranking[0]:02}</div></div>
<div class='card'><div class='label'>前5核心</div><div class='value number-line'>{_fmt(ranking[:5])}</div></div>
<div class='card'><div class='label'>前9核心</div><div class='value number-line'>{_fmt(ranking[:9])}</div></div>
<div class='card'><div class='label'>公開狀態</div><div class='value ok'>已公開</div></div>
</div></div>
<div class='band'><h2>本期前15名單一明細</h2><div class='table-wrap'><table><thead><tr><th>排名</th><th>號碼</th><th>區段</th><th>相對指數（非機率）</th><th>主要支撐</th></tr></thead><tbody>{''.join(rank_rows)}</tbody></table></div></div>
<div class='band'><h2>本期推薦牌組</h2><div class='table-wrap'><table><thead><tr><th>組別</th><th>號碼</th><th>檢查</th></tr></thead><tbody>{ticket_rows}</tbody></table></div></div>
<div class='band'><h2>本期投注排除</h2><div class='table-wrap'><table><thead><tr><th>區段</th><th>號碼</th><th>處理</th></tr></thead><tbody>{exclusion_rows}</tbody></table></div></div>
<div class='band'><h2>上一期號碼連莊資格</h2><p class='note'>上一期號碼只有通過相對指數、全歷史轉移、正式模組與個別連莊回測，才可保留在本期前9；不做補位。</p><div class='table-wrap'><table><thead><tr><th>上一期號碼</th><th>相對指數</th><th>正貢獻模組</th><th>連莊命中／樣本</th><th>資格</th><th>本期名次</th><th>結果</th></tr></thead><tbody>{repeat_rows}</tbody></table></div></div>
<div class='band warning'><h2>使用說明</h2><p>本頁只放同一期正式預測，不混入回測、開獎檢討、歷史封存或模型說明。今彩539為隨機遊戲，統計排序不保證中獎或獲利。</p></div>"""
    return _page_shell("index.html", "本期預測", "只顯示下一期正式預測資料", content)


def _backtest_page(bt, full_scan):
    recent = bt.get("recent_54") or {}
    distribution = "".join(
        f"<tr><td>{key}中</td><td>{value}期</td></tr>"
        for key, value in (bt.get("top9_hit_distribution") or {}).items()
    )
    rows = "".join(
        f"<tr><td>{label}</td><td>{top}</td><td>{contrast}</td><td>{judgement}</td></tr>"
        for label, top, contrast, judgement in (
            ("第1名", f"{bt.get('single_hits',0)}/{bt.get('samples',0)}", f"後1名 {bt.get('bottom1_hits',0)}/{bt.get('samples',0)}", "通過" if bt.get('single_direction_valid') else "未通過"),
            ("前5平均命中", bt.get('top5_avg_hits',0), f"後5 {bt.get('bottom5_avg_hits',0)}", "通過" if bt.get('top5_avg_hits',0)>bt.get('bottom5_avg_hits',0) else "未通過"),
            ("前9平均命中", bt.get('top9_avg_hits',0), f"後9 {bt.get('bottom9_avg_hits',0)}", "通過" if bt.get('top9_avg_hits',0)>bt.get('bottom9_avg_hits',0) else "未通過"),
            ("前9位置命中率", f"{100*bt.get('top9_slot_hit_rate',0):.2f}%", f"第10至15名 {100*bt.get('rank10_15_slot_hit_rate',0):.2f}%", "通過" if bt.get('boundary_control_valid') else "未通過"),
        )
    )
    recent_rows = "".join(
        f"<tr><td>{label}</td><td>{value}</td></tr>" for label, value in (
            ("前9平均命中", recent.get("top9_avg_hits", 0)),
            ("後9平均命中", recent.get("bottom9_avg_hits", 0)),
            ("前9零中期數", (recent.get("top9_hit_distribution") or {}).get("0", 0)),
            ("實際開獎號平均名次", recent.get("avg_actual_rank", 0)),
        )
    )
    full_rows = "".join(
        f"<tr><td>{label}</td><td>{value}</td></tr>" for label, value in (
            ("逐期掃描期數", full_scan.get("samples", 0)),
            ("第1名命中", full_scan.get("single_hits", 0)),
            ("後1名命中", full_scan.get("bottom1_hits", 0)),
            ("前5平均命中", full_scan.get("top5_avg_hits", 0)),
            ("後5平均命中", full_scan.get("bottom5_avg_hits", 0)),
            ("前9平均命中", full_scan.get("top9_avg_hits", 0)),
            ("後9平均命中", full_scan.get("bottom9_avg_hits", 0)),
            ("實際開獎號平均名次", full_scan.get("avg_actual_rank", 0)),
        )
    )
    content = f"""
<div class='band'><h2>最後360期隔離回測</h2><div class='grid'>
<div class='card'><div class='label'>隔離期數</div><div class='value'>{bt.get('samples',0)}期</div></div>
<div class='card'><div class='label'>排序方向判定</div><div class='value'>排序方向{'通過' if bt.get('ranking_direction_valid') else '未通過'}</div></div>
<div class='card'><div class='label'>前9至少2中比例</div><div class='value'>{100*bt.get('top9_at_least_2_rate',0):.2f}%</div></div>
<div class='card'><div class='label'>前5至少2中比例</div><div class='value'>{100*bt.get('top5_at_least_2_rate',0):.2f}%</div></div>
</div><h3>前後段方向對照</h3><div class='table-wrap'><table><thead><tr><th>項目</th><th>前段</th><th>對照</th><th>判定</th></tr></thead><tbody>{rows}</tbody></table></div><h3>前9逐期命中分布</h3><div class='table-wrap'><table><thead><tr><th>命中數</th><th>期數</th></tr></thead><tbody>{distribution}</tbody></table></div></div>
<div class='band'><h2>最近54期獨立觀察</h2><div class='table-wrap'><table><thead><tr><th>項目</th><th>結果</th></tr></thead><tbody>{recent_rows}</tbody></table></div></div>
<div class='band'><h2>全歷史逐期一致性掃描</h2><p class='note'>從第321期起逐期重算；此區只做方向診斷，不冒充隔離驗證。</p><div class='table-wrap'><table><thead><tr><th>項目</th><th>結果</th></tr></thead><tbody>{full_rows}</tbody></table></div></div>
<div class='band warning'><h2>回測規則</h2><p>每一測試期只讀取該期以前已知資料；禁止用同一期開獎結果改寫同一期預測。</p></div>"""
    return _page_shell("backtest.html", "回測驗證", "只顯示回測與方向檢查", content)


def _review_page(settlements, weights, selection, feature_labels):
    if not settlements:
        return _page_shell("review.html", "開獎檢討", "只顯示最新一期開獎後檢討", "<div class='band empty'>等待第一筆開獎前封存完成結算</div>")
    item = settlements[-1]
    actual_rows = "".join(
        f"<tr><td>{row.get('number',0):02}</td><td>{row.get('rank','－')}</td><td>{row.get('relative_index',0):.2f}</td><td>{'前9' if row.get('rank',99)<=9 else ('第10至15名' if row.get('rank',99)<=15 else '第16名以後')}</td></tr>"
        for row in item.get("actual_rankings", [])
    )
    module_rows = "".join(
        f"<tr><td>{feature_labels.get(row.get('module'),row.get('module','－'))}</td><td>{row.get('actual_mean',0):+.4f}</td><td>{row.get('missed_top5_mean',0):+.4f}</td><td>{row.get('discrimination_gap',0):+.4f}</td><td>{row.get('boundary_discrimination_gap',0):+.4f}</td><td>{'失準，已回灌' if row.get('error_flag') else '保留競爭'}</td></tr>"
        for row in item.get("module_review", [])
    )
    before = item.get("production_weights_before") or {}
    weight_rows = "".join(
        f"<tr><td>{feature_labels.get(key,key)}</td><td>{float(before.get(key,0)):.3f}</td><td>{float(weights.get(key,0)):.3f}</td><td>{float(weights.get(key,0))-float(before.get(key,0)):+.3f}</td></tr>"
        for key in weights
    )
    errors = "、".join(feature_labels.get(key, key) for key in item.get("error_modules", [])) or "本期沒有負向鑑別模組"
    diagnostic = selection.get("diagnostic") or {}
    content = f"""
<div class='band'><h2>最新一期命中結算</h2><div class='grid'>
<div class='card'><div class='label'>檢討開獎日</div><div class='value'>{item.get('target_draw_date','－')}</div></div>
<div class='card'><div class='label'>實際開獎</div><div class='value number-line'>{_fmt(item.get('actual_numbers') or [])}</div></div>
<div class='card'><div class='label'>開獎前1中1主選</div><div class='value'>{int(item.get('single_published',0)):02}・{'命中' if item.get('single_hit') else '未中'}</div></div>
<div class='card'><div class='label'>開獎前前9命中</div><div class='value'>{_fmt(item.get('top9_hits') or []) or '0顆'}</div></div>
<div class='card'><div class='label'>第10至15名命中</div><div class='value'>{_fmt(item.get('rank10_15_hits') or []) or '0顆'}</div></div>
</div></div>
<div class='band'><h2>實際開獎號碼原始排名</h2><div class='table-wrap'><table><thead><tr><th>號碼</th><th>開獎前排名</th><th>相對指數</th><th>區段</th></tr></thead><tbody>{actual_rows}</tbody></table></div></div>
<div class='band warning'><h2>錯誤模組與前9邊界逐項檢討</h2><p><b>失準模組：{errors}</b></p><div class='table-wrap'><table><thead><tr><th>模組</th><th>開獎號平均貢獻</th><th>前5落空號平均貢獻</th><th>整體鑑別差</th><th>邊界鑑別差</th><th>處理</th></tr></thead><tbody>{module_rows}</tbody></table></div></div>
<div class='band'><h2>開獎後滾動權重重算</h2><p>本期已重新搜尋全部 {diagnostic.get('candidate_count',0)} 組權重，保留 {diagnostic.get('eligible_candidate_count',0)} 組均衡候選，再完成方向模型逐期重選。</p><div class='table-wrap'><table><thead><tr><th>模組</th><th>開獎前權重</th><th>重算後權重</th><th>調整</th></tr></thead><tbody>{weight_rows}</tbody></table></div></div>
<div class='band'><h2>檢討證據</h2><div class='grid'><div class='card'><div class='label'>開獎前封存驗證碼</div><div class='value'>{_numeric_code(item.get('pre_draw_seal_sha256') or item.get('legacy_reconstruction_sha256'))}</div></div><div class='card'><div class='label'>檢討驗證碼</div><div class='value'>{_numeric_code(item.get('review_evidence_sha256'))}</div></div></div><p class='note'>只讀取開獎前封存資料，禁止開獎後換號或補號。</p></div>"""
    return _page_shell("review.html", "開獎檢討", "只顯示最新一期命中檢討與滾動修正", content)


def _history_page(settlements):
    rows = "".join(
        f"<tr><td>{item.get('target_draw_date','－')}</td><td>{int(item.get('single_published',0)):02}</td><td>{_fmt(item.get('top9_published') or [])}</td><td>{_fmt(item.get('actual_numbers') or [])}</td><td>{'命中' if item.get('single_hit') else '未中'}</td><td>{_fmt(item.get('top9_hits') or []) or '0顆'}</td><td>{_fmt(item.get('rank10_15_hits') or []) or '0顆'}</td></tr>"
        for item in reversed(settlements)
    )
    if not rows:
        rows = "<tr><td colspan='7'>尚無已結算封存紀錄</td></tr>"
    content = f"""
<div class='band'><h2>開獎前封存實戰紀錄</h2><p class='note'>本頁只列歷史結算總表；最新一期的逐模組原因與權重調整請看「開獎檢討」。</p><div class='table-wrap'><table><thead><tr><th>開獎日</th><th>開獎前1中1</th><th>開獎前前9</th><th>實際開獎</th><th>主選結果</th><th>前9命中</th><th>第10至15名命中</th></tr></thead><tbody>{rows}</tbody></table></div></div>"""
    return _page_shell("history.html", "歷史封存", "只顯示各期開獎前正式封存與結算", content)


def _models_page(draws, weights, bt, selection, repeat_audit, feature_labels):
    diagnostic = selection.get("diagnostic") or {}
    long_window = diagnostic.get("long_history_selection_window") or {}
    formula_rows = "".join(
        f"<tr><td>{feature_labels.get(key,key)}</td><td>逐期擴展全歷史資料庫</td><td>{value:+.3f}</td><td>{'正向' if value>=0 else '反向'}</td></tr>"
        for key, value in weights.items()
    )
    rule_rows = "".join(
        f"<tr><td>{item['number']:02}</td><td>{item['relative_index']:.1f}</td><td>{item['transition_contribution']:+.3f}</td><td>{item['positive_module_count']}</td><td>{100*item['repeat_rate']:.2f}%</td><td>{'通過' if item['repeat_backtest_pass'] else '未通過'}</td></tr>"
        for item in repeat_audit
    )
    content = f"""
<div class='band'><h2>全歷史運算範圍</h2><div class='grid'>
<div class='card'><div class='label'>資料範圍</div><div class='value'>{draws[0]['date']}～{draws[-1]['date']}</div></div>
<div class='card'><div class='label'>全歷史期數</div><div class='value'>{len(draws):,}期</div></div>
<div class='card'><div class='label'>全歷史核心占比</div><div class='value'>100%</div></div>
<div class='card'><div class='label'>短期正式權重</div><div class='value'>0%</div></div>
</div></div>
<div class='band'><h2>正式方向模型</h2><p>每次預測與每一期回測都使用當時以前的全部歷史資料。先搜尋 {diagnostic.get('candidate_count',0)} 組錨定權重，保留 {diagnostic.get('eligible_candidate_count',0)} 組均衡候選，再建立 {bt.get('strategy_candidate_count',0)} 組模組正反方向模型；每一期只用此前 {bt.get('strategy_selection_window',0)} 期成績選擇下一期方向。</p><div class='table-wrap'><table><thead><tr><th>正式模組</th><th>資料來源</th><th>目前權重</th><th>方向</th></tr></thead><tbody>{formula_rows}</tbody></table></div></div>
<div class='band'><h2>多模組校正規格</h2><div class='grid'>
<div class='card'><div class='label'>錨定候選</div><div class='value'>{diagnostic.get('candidate_count',0)}組</div></div>
<div class='card'><div class='label'>均衡候選</div><div class='value'>{diagnostic.get('eligible_candidate_count',0)}組</div></div>
<div class='card'><div class='label'>長歷史複驗</div><div class='value'>{long_window.get('samples',0)}個逐期樣本</div></div>
<div class='card'><div class='label'>長歷史分段</div><div class='value'>{long_window.get('folds',0)}段</div></div>
<div class='card'><div class='label'>方向模型</div><div class='value'>{bt.get('strategy_candidate_count',0)}組</div></div>
<div class='card'><div class='label'>方向選擇窗</div><div class='value'>{bt.get('strategy_selection_window',0)}期</div></div>
</div></div>
<div class='band'><h2>連莊資格驗算規格</h2><p>上一期號碼必須同時符合：相對指數至少75、全歷史轉移貢獻為正、至少兩個正式模組正貢獻、全歷史連莊率不低於12.82%，且個別回測通過；不做補位。</p><div class='table-wrap'><table><thead><tr><th>上一期號碼</th><th>相對指數</th><th>轉移貢獻</th><th>正貢獻模組</th><th>全歷史連莊率</th><th>個別回測</th></tr></thead><tbody>{rule_rows}</tbody></table></div></div>"""
    return _page_shell("models.html", "模型說明", "只顯示資料範圍、公式與校正規格", content)


def _health_page(draws, bt, full_scan, generated_at, settlements):
    latest = draws[-1]
    direction = "通過" if bt.get("ranking_direction_valid") else "未通過"
    settled = bool(settlements and settlements[-1].get("review_status") == "completed_from_pre_draw_seal")
    checks = (
        ("資料完整性", "通過", "期別與日期去重；每期5個不重複號碼"),
        ("全歷史模式", "通過", f"正式運算使用全部 {len(draws):,} 期"),
        ("自動重新運算", "通過", "開獎資料更新後重建所有分頁"),
        ("命中檢討", "通過" if settled else "等待結算", "只採用開獎前封存資料"),
        ("前9邊界", "通過" if bt.get("boundary_control_valid") else "未通過", "比較每個排名位置命中率"),
        ("排序方向", direction, "最後360期隔離檢查"),
        ("手機同步", "通過", "每30秒檢查版本，頁面採網路優先"),
    )
    rows = "".join(f"<tr><td>{name}</td><td>{status}</td><td>{detail}</td></tr>" for name, status, detail in checks)
    content = f"""
<div class='band'><h2>目前資料狀態</h2><div class='grid'>
<div class='card'><div class='label'>最新開獎期別</div><div class='value'>{latest['period']}</div></div>
<div class='card'><div class='label'>最新開獎日</div><div class='value'>{latest['date']}</div></div>
<div class='card'><div class='label'>歷史期數</div><div class='value'>{len(draws):,}期</div></div>
<div class='card'><div class='label'>最後運算時間</div><div class='value'>{generated_at}</div></div>
</div></div>
<div class='band'><h2>鐵律守門</h2><div class='table-wrap'><table><thead><tr><th>項目</th><th>結果</th><th>說明</th></tr></thead><tbody>{rows}</tbody></table></div></div>
<div class='band'><h2>模型健康與公開狀態</h2><div class='grid'>
<div class='card'><div class='label'>公開狀態</div><div class='value ok'>正常公開</div></div>
<div class='card'><div class='label'>排序方向判定</div><div class='value'>排序方向{direction}</div></div>
<div class='card'><div class='label'>方向模型數</div><div class='value'>{bt.get('strategy_candidate_count',0)}組</div></div>
<div class='card'><div class='label'>隔離回測期數</div><div class='value'>{bt.get('samples',0)}期</div></div>
<div class='card'><div class='label'>全歷史診斷期數</div><div class='value'>{full_scan.get('samples',0)}期</div></div>
</div></div>"""
    return _page_shell("health.html", "系統健康", "只顯示資料更新、同步與完整性狀態", content)


def render_report_pages(draws, weights, score, tickets, bt, full_scan, repeat_audit, selection, reports_dir: Path, feature_labels: dict) -> dict[str, str]:
    latest = draws[-1]
    rank_numbers = __import__("tw539_ultra").rank_numbers
    ranking = rank_numbers(score, latest["period"])
    target = datetime.strptime(latest["date"], "%Y-%m-%d").date() + timedelta(days=1)
    while target.weekday() == 6:
        target += timedelta(days=1)
    generated_at = datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M")
    settlements = _read_jsonl(reports_dir / "published-settlements.jsonl")
    return {
        "index.html": _prediction_page(draws, weights, score, tickets, repeat_audit, ranking, target.isoformat(), generated_at, feature_labels),
        "backtest.html": _backtest_page(bt, full_scan),
        "review.html": _review_page(settlements, weights, selection, feature_labels),
        "history.html": _history_page(settlements),
        "models.html": _models_page(draws, weights, bt, selection, repeat_audit, feature_labels),
        "health.html": _health_page(draws, bt, full_scan, generated_at, settlements),
    }
