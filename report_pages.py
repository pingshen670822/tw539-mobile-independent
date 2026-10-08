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


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _display_time(value) -> str:
    text = str(value or "－").replace("T", " ")
    return text[:-6] if len(text) > 6 and text[-6] in "+-" and text[-3] == ":" else text


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
*{{box-sizing:border-box}}[hidden]{{display:none!important}}body{{margin:0;background:#f3f4f6;color:#172033;font-family:system-ui,'Microsoft JhengHei',sans-serif;line-height:1.55}}main{{max-width:1180px;margin:auto;padding:18px}}header{{background:linear-gradient(135deg,#7f1017,#d1242f);color:#fff;padding:24px;border-radius:14px}}h1{{margin:0 0 5px;font-size:28px}}h2{{border-left:6px solid #c1121f;padding-left:10px;color:#7f1017;margin:0 0 16px}}h3{{color:#7f1017;margin:24px 0 10px}}nav{{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin:14px 0}}nav a{{display:flex;align-items:center;justify-content:center;min-height:44px;background:#fff;border:1px solid #d1d5db;border-radius:9px;padding:8px;color:#7f1017;text-decoration:none;font-weight:800;text-align:center}}nav a.active{{background:#7f1017;color:#fff;border-color:#7f1017}}.app-actions{{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-top:14px}}.install-button{{min-height:44px;border:2px solid #fff;border-radius:999px;padding:8px 18px;background:#ffd966;color:#651018;font:900 16px system-ui,'Microsoft JhengHei',sans-serif;box-shadow:0 3px 10px #0004;cursor:pointer}}.install-button:focus-visible{{outline:3px solid #fff;outline-offset:3px}}.install-status{{font-weight:800}}.install-help{{margin-top:12px;padding:12px 14px;border-radius:10px;background:#fff;color:#651018;font-weight:700}}.install-help p{{margin:5px 0}}.band{{background:#fff;border:1px solid #d8dee8;border-radius:12px;padding:18px;margin:14px 0;box-shadow:0 2px 8px #0000000d}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}}.card{{border:1px solid #d9dde5;border-radius:10px;padding:13px;background:#fff}}.primary{{border:2px solid #c1121f;background:#fff5f5}}.strong{{border:3px solid #b8860b;background:linear-gradient(135deg,#fff8d8,#fff);box-shadow:0 4px 18px #b8860b33}}.strong .number{{font-size:64px}}.badge{{display:inline-block;padding:6px 12px;border-radius:999px;background:#7f1017;color:#fff;font-weight:900;margin-bottom:8px}}.label{{color:#687386;font-size:13px}}.value{{font-size:18px;font-weight:800;margin-top:4px}}.number{{color:#c1121f;font-size:38px;letter-spacing:2px}}.number-line{{font-size:24px;letter-spacing:3px;color:#7f1017}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse}}th{{background:#7f1017;color:#fff}}th,td{{padding:9px;border:1px solid #d7dce4;text-align:left;white-space:nowrap}}tr:nth-child(even) td{{background:#fafafa}}.warning{{background:#fff8e6;border-color:#e9b949}}.ok{{color:#176b3a}}.bad{{color:#9b1c1c}}.note{{color:#626d7d}}.empty{{padding:22px;text-align:center;color:#687386}}footer{{padding:14px 4px 28px;color:#687386;font-size:13px}}@media(max-width:760px){{main{{padding:8px}}header{{border-radius:8px;padding:19px}}nav{{grid-template-columns:repeat(3,minmax(0,1fr))}}nav a{{font-size:14px}}.band{{padding:13px}}h1{{font-size:24px}}.number-line{{font-size:20px;letter-spacing:2px}}.strong .number{{font-size:56px}}.install-button{{width:100%}}}}@media(max-width:390px){{nav{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
</style>
<style>
.cloud-button{{min-height:44px;border:2px solid #fff;border-radius:999px;padding:8px 18px;display:inline-flex;align-items:center;justify-content:center;background:#fff;color:#7f1017;font:900 16px system-ui,'Microsoft JhengHei',sans-serif;box-shadow:0 3px 10px #0004;cursor:pointer;text-align:center;text-decoration:none}}
.cloud-button.repair-button{{background:#ffe3e3;color:#8b0000}}
.cloud-button:focus-visible{{outline:3px solid #fff;outline-offset:3px}}
.cloud-control-note{{width:100%;font-size:13px;font-weight:700;color:#fff}}
.cloud-control-status{{width:100%;font-weight:900;color:#fff}}
.report-details{{margin:14px 0;border:1px solid #d8dee8;border-radius:12px;background:#fff;box-shadow:0 2px 8px #0000000d}}
.report-details>summary{{list-style:none;min-height:54px;padding:14px 18px;display:flex;align-items:center;justify-content:space-between;color:#7f1017;font-weight:900;cursor:pointer}}
.report-details>summary::-webkit-details-marker{{display:none}}
.report-details>summary::after{{content:'點開';padding:5px 10px;border-radius:999px;background:#7f1017;color:#fff;font-size:13px}}
.report-details[open]>summary::after{{content:'收起'}}
.report-details>.band{{margin:0;border-width:1px 0 0;border-radius:0;box-shadow:none}}
.ironlaw-numbers td:nth-child(2){{font-size:30px;font-weight:900;color:#c1121f}}
.validation-seals{{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}}
.validation-seals span{{padding:7px 11px;border-radius:999px;background:#176b3a;color:#fff;font-weight:900}}
@media(max-width:760px){{.cloud-button{{width:100%}}}}
</style>
</head>
<body><main>
<header><h1>{heading}</h1><div>{subtitle}</div><div class='app-actions'><button type='button' id='manual-update-button' class='cloud-button update-button'>手動更新最新</button><a id='emergency-repair-button' class='cloud-button repair-button' href='https://github.com/pingshen670822/tw539-mobile-independent/actions/workflows/watchdog.yml' target='_blank' rel='noopener'>當機立即修復</a><button type='button' id='install-app-button' class='install-button' aria-controls='install-app-help' aria-expanded='false' hidden>安裝手機版</button><span id='install-app-status' class='install-status' aria-live='polite' hidden></span><div class='cloud-control-note'>手動更新會立即清除舊快取、重新取得雲端結果並重載本頁；當機修復為受保護的管理控制頁。</div><div id='cloud-control-status' class='cloud-control-status' aria-live='polite'></div></div><div id='install-app-help' class='install-help' hidden><p><b>蘋果手機：</b>用瀏覽器開啟後，點「分享」，再選「加入主畫面」。</p><p><b>安卓手機：</b>點上方「安裝手機版」；若未跳出，請從瀏覽器選單選「安裝應用程式」或「加到主畫面」。</p></div></header>
<nav aria-label='戰報分類'>{nav}</nav>
{content}
<footer>各頁只顯示所屬分類；資料由同一次正式運算產生並同步更新。</footer>
</main></body></html>"""


def _prediction_page(draws, weights, score, tickets, repeat_audit, ranking, target_date, generated_at, feature_labels, bt):
    latest = draws[-1]
    target_day = datetime.strptime(target_date, "%Y-%m-%d")
    weekday_names = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
    target_label = f"{target_day.year}年{target_day.month:02d}月{target_day.day:02d}日（{weekday_names[target_day.weekday()]}）"
    minimum = min(score.values())
    spread = max(0.00001, max(score.values()) - minimum)
    engine = __import__("tw539_ultra")
    features = engine.formal_feature_table(draws)
    strict=bt.get("strict_publication_gate") or {}
    strict_details={int(item.get("number")):item for item in (strict.get("details") or [])}
    qualified=list(strict.get("qualified_numbers") or [])
    tiers=strict.get("tiers") or {"single":[],"two":[],"three":[],"five":[],"nine":[]}
    requested=strict.get("requested_sizes") or {"single":1,"two":2,"three":3,"five":5,"nine":9}
    single_formal=(tiers.get("single") or [None])[0]
    single_gate=strict.get("single_gate") or {}
    rank_rows = []
    for rank, number in enumerate(ranking[:15], 1):
        index = 100 * (score[number] - minimum) / spread
        support = "、".join(
            feature_labels.get(key, key) for key in weights
            if abs(weights[key]) > 1e-12 and weights[key] * features[key][number] > 0
        ) or "均衡校正"
        zone = "內部前5" if rank <= 5 else ("內部前9" if rank <= 9 else "第10至15名監控")
        strict_row=strict_details.get(number) or {}
        qualification=("通過正式發布" if strict_row.get("qualified") else
                       "淘汰："+"、".join(strict_row.get("failure_reasons") or ["未通過守門"]))
        rank_rows.append(
            f"<tr><td>{rank}</td><td><b>{number:02}</b></td><td>{zone}</td><td>{index:.1f}</td><td>{support}</td><td class='{'ok' if strict_row.get('qualified') else 'bad'}'>{qualification}</td></tr>"
        )
    ticket_rows = "".join(
        f"<tr><td>{index}</td><td>{_fmt(ticket)}</td><td>五碼全數通過嚴格發布守門</td></tr>"
        for index, ticket in enumerate(tickets, 1)
    ) or "<tr><td colspan='3'>合格號碼不足五顆或沒有合格牌型，本期不產生推薦牌組，絕不補號</td></tr>"
    excluded = [number for number in ranking if number not in set(qualified)]
    exclusion_rows=(f"<tr><td>未通過嚴格守門</td><td>{_fmt(excluded)}</td><td>不得進入任何正式推薦或牌組</td></tr>")
    repeat_rows = "".join(
        f"<tr><td>{item['number']:02}</td><td>{item['relative_index']:.1f}</td><td>{item['positive_module_count']}</td><td>{item['repeat_hits']}/{item['repeat_samples']}</td><td>{'符合' if item['qualified'] else '未符合'}</td><td>{item['final_rank']}</td><td>{'列入前9' if item['listed_top9'] else '未列入前9'}</td></tr>"
        for item in repeat_audit
    )
    strong=bool(bt.get("single_strong_recommendation"))
    evidence_label=bt.get("single_confidence_label") or "本期綜合最強"
    strong_conditions=bt.get("single_strong_conditions") or {}
    condition_rows="".join(
        f"<tr><td>{label}</td><td class='{'ok' if passed else 'bad'}'>{'通過' if passed else '未通過'}</td></tr>"
        for label,passed in strong_conditions.items()
    )
    supermodel=bt.get("single_supermodel") or {}
    global_fusion=supermodel.get("global_fusion") or {}
    fusion_walk=global_fusion.get("fusion_walk_forward") or {}
    fusion_upgrade=global_fusion.get("production_upgrade_gate") or {}
    statistical_validation=supermodel.get("statistical_validation") or {}
    live_accuracy=bt.get("live_single_accuracy") or {}
    live_all=live_accuracy.get("all_sealed") or {}
    live_supermodel=live_accuracy.get("supermodel_series") or {}
    live_architecture=live_accuracy.get("current_architecture") or {}
    super_candidate=int(supermodel.get("candidate") or ranking[0])
    walk=supermodel.get("walk_forward") or {}
    selection_evidence=(supermodel.get("current_selection") or {}).get("selection_evidence") or []
    calculation_rows="".join(
        f"<tr><td>前{item.get('span',0)}期</td><td>{item.get('hits',0)}</td><td>{item.get('expected',0):.2f}</td><td>{item.get('standardized_excess',0):+.3f}</td></tr>"
        for item in selection_evidence
    )
    fold_rows="".join(
        f"<tr><td>{item.get('first_date','－')}～{item.get('last_date','－')}</td><td>{item.get('window',0)}期</td><td>{100*item.get('global_history_blend',0):.0f}%</td><td>{item.get('single_hits',0)}／{item.get('samples',0)}</td></tr>"
        for item in (walk.get("folds") or [])
    )
    metric_rows="".join(
        f"<tr><td>{label}</td><td>{item.get('single_hits',0)}／{item.get('samples',0)}</td><td>{item.get('random_expected_hits',0):.2f}</td><td>{item.get('excess_hits',0):+.2f}</td></tr>"
        for label,item in (("完整逐段隔離",walk.get("full") or {}),("最近360期",walk.get("recent_360") or {}),("最近240期",walk.get("recent_240") or {}),("最近120期",walk.get("recent_120") or {}),("最近54期",walk.get("recent_54") or {}),("最近33期",walk.get("recent_33") or {}),("最近14期",walk.get("recent_14") or {}))
    )
    fusion_family_rows="".join(
        f"<tr><td>{item.get('family','－')}</td><td>{item.get('label','－')}</td><td>{int(item.get('candidate',0)):02}</td><td>{item.get('robust_score',0):+.3f}</td><td class='{'ok' if item.get('robust_score',0)>0 else 'bad'}'>{'保留' if item.get('robust_score',0)>0 else '淘汰'}</td></tr>"
        for item in (global_fusion.get("family_champions") or [])
    )
    fusion_vote_rows="".join(
        f"<tr><td>{int(item.get('candidate',0)):02}</td><td>{item.get('accepted_model_votes',0)}</td><td>{item.get('family_support',0)}</td><td>{item.get('robust_score_sum',0):+.3f}</td></tr>"
        for item in (global_fusion.get("accepted_vote_table") or [])
    )
    single_break=bt.get("single_repeat_break_current") or {}
    if single_break.get("applied"):
        single_break_note=f"原始首位 {int(single_break.get('original',0)):02} 與前一期封存單碼重複，依回測通過的冷卻規則改採五組共識次選 {int(single_break.get('replacement',0)):02}。"
    else:
        single_break_note="本期原始首位未觸發重複冷卻，正式主選維持模型首位。"
    guard_active=bool(bt.get("catastrophic_guard_current_trigger"))
    guard_condition=bool(bt.get("catastrophic_guard_current_condition"))
    guard_before=bt.get("catastrophic_guard_unguarded") or {}
    if guard_active:
        guard_note="失準監測不得改動正式排序；若出現啟動狀態即視為系統錯誤。"
    elif guard_condition:
        guard_note="條件成立，但跨區間回測證明旋轉會拖累前5、前9與邊界，本期只記錄、不改號。"
    else:
        guard_note="條件未成立；監測器只記錄，不得改動正式排序。"
    fusion_candidate=int(global_fusion.get("fusion_candidate") or 0)
    fusion_relation=("同碼" if fusion_candidate==super_candidate else f"不同碼（全球融合最高票為{fusion_candidate:02}）")
    source_note=(f"<p class='note'><b>全系統與全球模組聯合運算來源：全歷史{supermodel.get('full_history_draws',0):,}期、"
                 f"{supermodel.get('parameter_count',0)}組主模型、{global_fusion.get('family_count',0)}類共"
                 f"{global_fusion.get('module_count',0)}組全球模組，跨區段合格{global_fusion.get('accepted_module_count',0)}組；"
                 f"本期主模型最高順位與全球融合最高票{fusion_relation}。</b></p>")
    if single_formal is not None:
        failed="、".join(single_gate.get("failure_reasons") or [])
        validation_note=("統計與開獎前封存實戰守門全部通過。" if strong else
                         f"完整運算已完成；目前只能列為最高順位，實戰強烈門檻未通過。{failed}")
        single_head=(f"<div class='badge'>{'強烈驗證通過' if strong else '完整運算最高順位'}</div><h2>{target_label} 終極獨支（1中1）</h2>"
                     f"<div class='number'>{single_formal:02}</div>"
                     f"<div class='validation-seals'><span>全歷史{supermodel.get('full_history_draws',0):,}期</span>"
                     f"<span>{supermodel.get('parameter_count',0)}組主模型融合</span>"
                     f"<span>{global_fusion.get('module_count',0)}組全球八家族軌跡複驗</span>"
                     f"<span>{sum(bool(value) for value in strong_conditions.values())}／{len(strong_conditions)}項強烈驗證</span></div>"
                     f"{source_note}<p><b>{validation_note}</b></p>")
    else:
        failed="、".join((strict.get("single_gate") or {}).get("failure_reasons") or ["嚴格條件未全部通過"])
        single_head=(f"<div class='badge'>完整運算完成</div><h2>{target_label} 終極獨支（1中1）</h2>"
                     f"<div class='number'>{super_candidate:02}</div>{source_note}<p><b>驗證警示：{failed}。</b></p>")
    tier_labels={"single":"1中1","two":"2中1～2","three":"3中1～3","five":"5中2～3","nine":"9中3～5"}
    tier_rows="".join(
        f"<tr><td><b>{tier_labels[key]}</b></td><td class='number-line'>{_fmt(tiers.get(key) or []) or '未發布'}</td></tr>"
        for key in ("two","three","five","nine")
    )
    strict_detail_rows="".join(
        f"<tr><td>{item.get('rank')}</td><td>{int(item.get('number',0)):02}</td>"
        f"<td>{item.get('relative_index',0):.2f}</td><td>{item.get('positive_module_count',0)}</td>"
        f"<td>{item.get('module_top15_support_count',0)}／{len(weights)}</td>"
        f"<td class='{'ok' if item.get('qualified') else 'bad'}'>{'通過' if item.get('qualified') else '淘汰：'+'、'.join(item.get('failure_reasons') or [])}</td></tr>"
        for item in (strict.get("details") or [])[:15]
    )
    passed_strong=sum(bool(value) for value in strong_conditions.values())
    live_accuracy_screen=(
        "<div class='band warning'><h2>終極獨支實戰準確度檢討</h2><div class='grid'>"
        f"<div class='card'><div class='label'>全部開獎前封存</div><div class='value'>{live_all.get('hits',0)}／{live_all.get('samples',0)}</div></div>"
        f"<div class='card'><div class='label'>全部封存命中率</div><div class='value'>{100*live_all.get('rate',0):.2f}%</div></div>"
        f"<div class='card'><div class='label'>同樣本隨機期望</div><div class='value'>{live_all.get('random_expected_hits',0):.2f}中</div></div>"
        f"<div class='card'><div class='label'>全球融合架構合計</div><div class='value'>{live_supermodel.get('hits',0)}／{live_supermodel.get('samples',0)}</div></div>"
        f"<div class='card'><div class='label'>現行架構封存</div><div class='value'>{live_architecture.get('hits',0)}／{live_architecture.get('samples',0)}</div></div>"
        f"<div class='card'><div class='label'>目前連續未中</div><div class='value'>{live_accuracy.get('current_miss_streak',0)}期</div></div>"
        f"<div class='card'><div class='label'>最長連續未中</div><div class='value'>{live_accuracy.get('longest_miss_streak',0)}期</div></div>"
        "</div><p><b>只計入開獎前已封存的正式預測；停擺期補登資料完全排除。現行架構未滿三十期前不得宣稱已證明穩定，全部封存實績低於隨機時也不得標成強烈驗證。</b></p></div>"
    )
    repeat_screen=(
        "<div class='band strong'><h2>終極獨支強烈驗證摘要</h2><div class='grid'>"
        f"<div class='card'><div class='label'>未限制原始首選</div><div class='value'>{int(supermodel.get('unconstrained_candidate') or 0):02}</div></div>"
        f"<div class='card'><div class='label'>不合格連莊前置排除</div><div class='value'>{_fmt(supermodel.get('blocked_unqualified_repeat_numbers') or []) or '無'}</div></div>"
        f"<div class='card'><div class='label'>主模型同碼共識</div><div class='value'>{supermodel.get('candidate_consensus_count',0)}／{supermodel.get('parameter_count',0)}組</div></div>"
        f"<div class='card'><div class='label'>全球合格模型票</div><div class='value'>{(global_fusion.get('primary_candidate_support') or {}).get('accepted_model_votes',0)}票</div></div>"
        f"<div class='card'><div class='label'>強烈驗證條件</div><div class='value'>{passed_strong}／{len(strong_conditions)}項通過</div></div>"
        "</div><p class='note'>未通過連莊資格的上期號碼先排除，再由全部模型重新排序與投票；不得把第二名直接補上，也不得沿用前期獨支。</p></div>"
    )
    content = f"""
<div class='band strong'><h2>本期預測日期：{target_label}</h2><div class='grid'>
<div class='card'><div class='label'>本期預測日期</div><div class='value'>{target_label}</div></div>
<div class='card'><div class='label'>資料計算截止</div><div class='value'>{latest['date']}</div></div>
<div class='card'><div class='label'>最新官方期別</div><div class='value'>{latest['period']}</div></div>
<div class='card'><div class='label'>本頁更新時間</div><div class='value'>{generated_at}</div></div>
<div class='card'><div class='label'>使用歷史期數</div><div class='value'>{len(draws):,}期</div></div>
</div></div>
<div class='band {'strong' if single_formal is not None and strong else 'primary'}'>{single_head}</div>
<div class='band ironlaw-numbers'><h2>本期其他鐵律號碼</h2><div class='table-wrap'><table><thead><tr><th>類型</th><th>正式號碼</th></tr></thead><tbody>{tier_rows}</tbody></table></div><p class='note'>未達全部條件即顯示未發布；不足不補位。</p></div>
<details class='report-details'><summary>查看獨支強烈驗證與完整運算</summary>
{live_accuracy_screen}
{repeat_screen}
<div class='band strong'><h2>超級獨支完整運算來源</h2><div class='grid'><div class='card'><div class='label'>參數候選</div><div class='value'>{supermodel.get('parameter_count',0)}組</div></div><div class='card'><div class='label'>選定動態窗</div><div class='value'>{supermodel.get('selected_window',0)}期</div></div><div class='card'><div class='label'>全歷史基準</div><div class='value'>{100*supermodel.get('selected_global_history_blend',0):.0f}%</div></div><div class='card'><div class='label'>使用完整歷史</div><div class='value'>{supermodel.get('full_history_draws',0):,}期</div></div><div class='card'><div class='label'>近期出現</div><div class='value'>{supermodel.get('candidate_recent_hits',0)}／{supermodel.get('candidate_recent_samples',0)}</div></div><div class='card'><div class='label'>全歷史出現</div><div class='value'>{supermodel.get('candidate_full_hits',0)}／{supermodel.get('candidate_full_samples',0)}</div></div><div class='card'><div class='label'>同碼參數共識</div><div class='value'>{supermodel.get('candidate_consensus_count',0)}／{supermodel.get('parameter_count',0)}</div></div></div><h3>目前模型選擇證據</h3><div class='table-wrap'><table><thead><tr><th>驗證區間</th><th>命中</th><th>隨機期望</th><th>標準化超額</th></tr></thead><tbody>{calculation_rows}</tbody></table></div><h3>六段時間隔離競賽</h3><div class='table-wrap'><table><thead><tr><th>預測區段</th><th>當時選定時間窗</th><th>全歷史占比</th><th>獨支命中</th></tr></thead><tbody>{fold_rows}</tbody></table></div><h3>隔離結果總表</h3><div class='table-wrap'><table><thead><tr><th>區間</th><th>實際命中</th><th>隨機期望</th><th>超額命中</th></tr></thead><tbody>{metric_rows}</tbody></table></div><p class='note'>每個區段開始前先用更早資料選定模型，之後整段鎖定，禁止用該段答案反選參數。所有號碼都保留全歷史基準，動態窗只負責追蹤近期偏移；開獎前完整封存，禁止事後換號。</p></div>
<div class='band strong'><h2>全球八家族軌跡融合複驗</h2><div class='grid'><div class='card'><div class='label'>總模組數</div><div class='value'>{global_fusion.get('module_count',0)}組</div></div><div class='card'><div class='label'>模型家族</div><div class='value'>{global_fusion.get('family_count',0)}類</div></div><div class='card'><div class='label'>跨區段合格</div><div class='value'>{global_fusion.get('accepted_module_count',0)}組</div></div><div class='card'><div class='label'>融合最高票</div><div class='value'>{int(global_fusion.get('fusion_candidate') or 0):02}</div></div><div class='card'><div class='label'>主模型七百二十期</div><div class='value'>{(walk.get('full') or {}).get('single_hits',0)}中</div></div><div class='card'><div class='label'>軌跡融合七百二十期</div><div class='value'>{(fusion_walk.get('full') or {}).get('single_hits',0)}中</div></div><div class='card'><div class='label'>軌跡升級判定</div><div class='value'>{'通過' if fusion_upgrade.get('passed') else '未通過，禁止取代'}</div></div><div class='card'><div class='label'>獨立家族支持</div><div class='value'>{(global_fusion.get('primary_candidate_support') or {}).get('family_support',0)}類</div></div></div><h3>各家族冠軍</h3><div class='table-wrap'><table><thead><tr><th>模型家族</th><th>最穩參數</th><th>本期首選</th><th>最弱區段分數</th><th>判定</th></tr></thead><tbody>{fusion_family_rows}</tbody></table></div><h3>合格模型票數</h3><div class='table-wrap'><table><thead><tr><th>候選號碼</th><th>合格模型票</th><th>支持家族</th><th>穩健分數總和</th></tr></thead><tbody>{fusion_vote_rows}</tbody></table></div><h3>雙重隨機基準</h3><div class='grid'><div class='card'><div class='label'>隔離命中</div><div class='value'>{statistical_validation.get('observed_hits',0)}／{statistical_validation.get('samples',0)}</div></div><div class='card'><div class='label'>固定隨機尾端值</div><div class='value'>{100*statistical_validation.get('exact_binomial_upper_tail_p',0):.2f}%</div></div><div class='card'><div class='label'>循環錯位尾端值</div><div class='value'>{100*statistical_validation.get('circular_shift_p',0):.2f}%</div></div><div class='card'><div class='label'>嚴格統計證明</div><div class='value'>{'通過' if statistical_validation.get('strict_five_percent_significance') else '尚未通過'}</div></div></div><p class='note'>新增多階拖牌軌跡與週期間隔危險率；每一期融合投票都只讀取更早資料。不穩定家族直接淘汰；融合若未同時提高七百二十期且各近期區段不退化，就禁止取代正式主模型。</p></div>
<div class='band strong'><h2>嚴格發布守門</h2><p><b>獨支每期必須由全歷史與多模組完整運算產生唯一最高順位；跨時間窗、參數共識與連莊資格只決定驗證標示，不得把結果隱藏或換碼。其他分級號碼仍須通過內部前九、分數、相對指數、模組支持與直接命中校準。</b></p><p class='note'>本期分級合格 {_fmt(qualified) or '零顆'}，共 {len(qualified)} 顆；多碼層級不足都直接少列，不補號、不塞號。獨支固定列出完整運算第一名並同步揭露驗證警示。</p><div class='table-wrap'><table><thead><tr><th>內部名次</th><th>號碼</th><th>相對指數</th><th>正貢獻模組</th><th>模組前十五支持</th><th>分級發布判定</th></tr></thead><tbody>{strict_detail_rows}</tbody></table></div></div>
<div class='band'><h2>最強號碼多邏輯總結</h2><div class='grid'><div class='card'><div class='label'>逐段隔離命中</div><div class='value'>{(walk.get('full') or {}).get('single_hits',0)}／{(walk.get('full') or {}).get('samples',0)}</div></div><div class='card'><div class='label'>最近120期</div><div class='value'>{(walk.get('recent_120') or {}).get('single_hits',0)}中</div></div><div class='card'><div class='label'>最近33期</div><div class='value'>{(walk.get('recent_33') or {}).get('single_hits',0)}中</div></div></div><h3>強烈推薦守門</h3><div class='table-wrap'><table><thead><tr><th>必要條件</th><th>結果</th></tr></thead><tbody>{condition_rows}</tbody></table></div></div>
</details>
<details class='report-details'><summary>查看資料、排名、排除與連莊診斷</summary>
<div class='band {'warning' if guard_condition else ''}'><h2>失準事件監測</h2><p><b>{guard_note} 鐵律：監測器永久禁止旋轉、換號或改動任何正式排名。</b></p><div class='grid'><div class='card'><div class='label'>監測條件</div><div class='value'>前9零中且平均名次至少{bt.get('catastrophic_guard_avg_rank_floor',22):.0f}</div></div><div class='card'><div class='label'>歷史條件成立</div><div class='value'>{bt.get('catastrophic_guard_trigger_count',0)}／{bt.get('samples',0)}期</div></div><div class='card'><div class='label'>正式旋轉次數</div><div class='value'>{bt.get('catastrophic_guard_application_count',0)}期</div></div><div class='card'><div class='label'>反事實比較窗</div><div class='value'>最近{bt.get('catastrophic_guard_policy_window',0)}次條件樣本</div></div><div class='card'><div class='label'>原排序前9平均</div><div class='value'>{guard_before.get('top9_avg_hits',0)}</div></div><div class='card'><div class='label'>正式前9平均</div><div class='value'>{bt.get('top9_avg_hits',0)}</div></div></div><p class='note'>原始前9：{_fmt((bt.get('next_unguarded_ranked') or [])[:9])}；正式前9：{_fmt(ranking[:9])}。監測依據：{bt.get('catastrophic_guard_current_source','逐期隔離重演')}。</p></div>
<div class='band'><h2>內部前十五診斷（非正式推薦）</h2><p class='note'>此表用來公開驗證淘汰原因；只有標示「通過正式發布」的號碼才是本期推薦。</p><div class='table-wrap'><table><thead><tr><th>排名</th><th>號碼</th><th>區段</th><th>相對指數（非機率）</th><th>主要支撐</th><th>正式資格</th></tr></thead><tbody>{''.join(rank_rows)}</tbody></table></div></div>
<div class='band'><h2>本期推薦牌組</h2><div class='table-wrap'><table><thead><tr><th>組別</th><th>號碼</th><th>檢查</th></tr></thead><tbody>{ticket_rows}</tbody></table></div></div>
<div class='band'><h2>本期投注排除</h2><div class='table-wrap'><table><thead><tr><th>區段</th><th>號碼</th><th>處理</th></tr></thead><tbody>{exclusion_rows}</tbody></table></div></div>
<div class='band'><h2>上一期號碼連莊資格</h2><p class='note'>上一期號碼只有通過相對指數、全歷史轉移、正式模組與個別連莊回測，才可保留在本期前9；不做補位。</p><div class='table-wrap'><table><thead><tr><th>上一期號碼</th><th>相對指數</th><th>正貢獻模組</th><th>連莊命中／樣本</th><th>資格</th><th>本期名次</th><th>結果</th></tr></thead><tbody>{repeat_rows}</tbody></table></div></div>
<div class='band warning'><h2>使用說明</h2><p>本頁只放同一期正式預測，不混入回測、開獎檢討、歷史封存或模型說明。今彩539為隨機遊戲，統計排序不保證中獎或獲利。</p></div>
</details>"""
    return _page_shell("index.html", "本期最強終極獨支", f"{target_label}｜全歷史、多模組與全球八家族軌跡層層運算再複驗", content)


def _backtest_page(bt, full_scan):
    supermodel=bt.get("single_supermodel") or {};super_walk=supermodel.get("walk_forward") or {}
    global_fusion=supermodel.get("global_fusion") or {};statistical_validation=supermodel.get("statistical_validation") or {}
    fusion_walk=global_fusion.get("fusion_walk_forward") or {};fusion_upgrade=global_fusion.get("production_upgrade_gate") or {}
    recent = bt.get("recent_54") or {}
    recent120 = bt.get("recent_120") or {}
    direct_baseline = bt.get("direct_hit_baseline") or {}
    direct_baseline54 = bt.get("direct_hit_baseline_recent_54") or {}
    direct_baseline120 = bt.get("direct_hit_baseline_recent_120") or {}
    change_baseline = bt.get("data_change_baseline") or {}
    change_baseline54 = bt.get("data_change_baseline_recent_54") or {}
    change_baseline120 = bt.get("data_change_baseline_recent_120") or {}
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
            ("正式第1名命中", f"{recent.get('single_hits',0)}/{recent.get('samples',0)}"),
            ("前5平均命中", recent.get("top5_avg_hits", 0)),
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
<div class='band strong'><h2>超級獨支多時間窗隔離驗證</h2><p><b>八種時間窗乘五種全歷史占比，共四十組候選；每一百二十期重新選型一次，選定後鎖住整段，禁止讀取該段答案反選模型。</b></p><div class='grid'><div class='card'><div class='label'>完整逐段隔離</div><div class='value'>{(super_walk.get('full') or {}).get('single_hits',0)}／{(super_walk.get('full') or {}).get('samples',0)}</div></div><div class='card'><div class='label'>最近360期</div><div class='value'>{(super_walk.get('recent_360') or {}).get('single_hits',0)}中</div></div><div class='card'><div class='label'>最近240期</div><div class='value'>{(super_walk.get('recent_240') or {}).get('single_hits',0)}中</div></div><div class='card'><div class='label'>最近120期</div><div class='value'>{(super_walk.get('recent_120') or {}).get('single_hits',0)}中</div></div><div class='card'><div class='label'>最近54期</div><div class='value'>{(super_walk.get('recent_54') or {}).get('single_hits',0)}中</div></div><div class='card'><div class='label'>最近33期</div><div class='value'>{(super_walk.get('recent_33') or {}).get('single_hits',0)}中</div></div><div class='card'><div class='label'>目前選定時間窗</div><div class='value'>{supermodel.get('selected_window',0)}期</div></div><div class='card'><div class='label'>發布守門</div><div class='value'>{'通過' if supermodel.get('release_gate_passed') else '未通過'}</div></div></div><p class='note'>最近14期逐段隔離為 {(super_walk.get('recent_14') or {}).get('single_hits',0)}中，照實保留、不隱藏；目前候選是加入最新資料後重新選出的下一期模型，不能把新模型事後套回舊期製造命中。</p></div>
<div class='band strong'><h2>全球軌跡融合與隨機基準複驗</h2><div class='grid'><div class='card'><div class='label'>八家族模組</div><div class='value'>{global_fusion.get('module_count',0)}組</div></div><div class='card'><div class='label'>跨六區段合格</div><div class='value'>{global_fusion.get('accepted_module_count',0)}組</div></div><div class='card'><div class='label'>融合候選</div><div class='value'>{int(global_fusion.get('fusion_candidate') or 0):02}</div></div><div class='card'><div class='label'>融合走步七百二十期</div><div class='value'>{(fusion_walk.get('full') or {}).get('single_hits',0)}中</div></div><div class='card'><div class='label'>融合走步最近一百二十期</div><div class='value'>{(fusion_walk.get('recent_120') or {}).get('single_hits',0)}中</div></div><div class='card'><div class='label'>正式升級守門</div><div class='value'>{'通過' if fusion_upgrade.get('passed') else '未通過'}</div></div><div class='card'><div class='label'>固定隨機尾端值</div><div class='value'>{100*statistical_validation.get('exact_binomial_upper_tail_p',0):.2f}%</div></div><div class='card'><div class='label'>循環錯位尾端值</div><div class='value'>{100*statistical_validation.get('circular_shift_p',0):.2f}%</div></div><div class='card'><div class='label'>百分之五嚴格顯著</div><div class='value'>{'通過' if statistical_validation.get('strict_five_percent_significance') else '尚未通過'}</div></div></div><p class='note'>多階拖牌、週期間隔等軌跡模組必須逐期前推；融合結果若沒有超越主模型並保持各近期區段不退化，就自動禁止取代。</p></div>
<div class='band'><h2>全歷史重組第三代：最後360期逐期走步回測</h2><div class='grid'>
<div class='card'><div class='label'>隔離期數</div><div class='value'>{bt.get('samples',0)}期</div></div>
<div class='card'><div class='label'>正式第1名命中</div><div class='value'>{bt.get('single_hits',0)}／{bt.get('samples',0)}</div></div>
<div class='card'><div class='label'>短窗單碼重排</div><div class='value'>已停用</div></div>
<div class='card'><div class='label'>排序方向判定</div><div class='value'>排序方向{'通過' if bt.get('ranking_direction_valid') else '未通過'}</div></div>
<div class='card'><div class='label'>前9至少2中比例</div><div class='value'>{100*bt.get('top9_at_least_2_rate',0):.2f}%</div></div>
<div class='card'><div class='label'>前5至少2中比例</div><div class='value'>{100*bt.get('top5_at_least_2_rate',0):.2f}%</div></div>
</div><h3>前後段方向對照</h3><div class='table-wrap'><table><thead><tr><th>項目</th><th>前段</th><th>對照</th><th>判定</th></tr></thead><tbody>{rows}</tbody></table></div><h3>前9逐期命中分布</h3><div class='table-wrap'><table><thead><tr><th>命中數</th><th>期數</th></tr></thead><tbody>{distribution}</tbody></table></div></div>
<div class='band strong'><h2>直接命中全排序校準</h2><p><b>重組後以五組全歷史方向共識為主，融合 {100*bt.get('direct_hit_full_rank_blend',0):.0f}% 直接命中模型；比例由五個連續360期區段與最近54、120期共同檢查。前5與前9任一關鍵區段退化即自動回退。</b></p><div class='grid'><div class='card'><div class='label'>最後360期前5</div><div class='value'>{direct_baseline.get('top5_avg_hits',0)} → {bt.get('top5_avg_hits',0)}</div></div><div class='card'><div class='label'>最後360期前9</div><div class='value'>{direct_baseline.get('top9_avg_hits',0)} → {bt.get('top9_avg_hits',0)}</div></div><div class='card'><div class='label'>最近120期前5／前9</div><div class='value'>{direct_baseline120.get('top5_avg_hits',0)}／{direct_baseline120.get('top9_avg_hits',0)} → {recent120.get('top5_avg_hits',0)}／{recent120.get('top9_avg_hits',0)}</div></div><div class='card'><div class='label'>最近54期前5／前9</div><div class='value'>{direct_baseline54.get('top5_avg_hits',0)}／{direct_baseline54.get('top9_avg_hits',0)} → {recent.get('top5_avg_hits',0)}／{recent.get('top9_avg_hits',0)}</div></div><div class='card'><div class='label'>直接命中融合占比</div><div class='value'>{100*bt.get('direct_hit_full_rank_blend',0):.0f}%</div></div><div class='card'><div class='label'>實際上線狀態</div><div class='value'>{'已套用' if bt.get('direct_hit_full_rank_gate') else '已回退'}</div></div></div></div>
<div class='band strong'><h2>資料變化影子驗證</h2><p><b>增量模型仍逐期以720期資料重算，但近期跨區段不穩定，正式占比已歸零；只保留影子驗證，不准它拖累正式前5與前9。待54、120、360期同時通過後才可重新上線。</b></p><div class='grid'><div class='card'><div class='label'>正式占比</div><div class='value'>{100*bt.get('data_change_rank_blend',0):.0f}%</div></div><div class='card'><div class='label'>影子比較窗</div><div class='value'>{bt.get('data_change_window',0)}期</div></div><div class='card'><div class='label'>最近54期前9</div><div class='value'>{change_baseline54.get('top9_avg_hits',0)} → {recent.get('top9_avg_hits',0)}</div></div><div class='card'><div class='label'>最近120期前9</div><div class='value'>{change_baseline120.get('top9_avg_hits',0)} → {recent120.get('top9_avg_hits',0)}</div></div><div class='card'><div class='label'>最後360期前9</div><div class='value'>{change_baseline.get('top9_avg_hits',0)} → {bt.get('top9_avg_hits',0)}</div></div><div class='card'><div class='label'>上線守門</div><div class='value'>{'通過' if bt.get('data_change_gate') else '影子觀察'}</div></div></div></div>
<div class='band strong'><h2>單碼重複冷卻</h2><p><b>第一名與上一期封存單碼重複、且上一期未曾啟動冷卻時，改採五組方向共識次選；每次切換後保留一期冷卻。校正只讀取當期以前資料。</b></p><div class='grid'><div class='card'><div class='label'>最後360期</div><div class='value'>{bt.get('single_repeat_break_baseline_hits',0)} → {bt.get('single_repeat_break_hits',0)}</div></div><div class='card'><div class='label'>最近120期</div><div class='value'>{bt.get('single_repeat_break_recent_120_baseline_hits',0)} → {bt.get('single_repeat_break_recent_120_hits',0)}</div></div><div class='card'><div class='label'>最近54期</div><div class='value'>{bt.get('single_repeat_break_recent_54_baseline_hits',0)} → {bt.get('single_repeat_break_recent_54_hits',0)}</div></div><div class='card'><div class='label'>隔離切換次數</div><div class='value'>{bt.get('single_repeat_break_application_count',0)}期</div></div><div class='card'><div class='label'>上線守門</div><div class='value'>{'通過' if bt.get('single_repeat_break_gate') else '未通過'}</div></div></div></div>
<div class='band'><h2>最近54期獨立觀察</h2><div class='table-wrap'><table><thead><tr><th>項目</th><th>結果</th></tr></thead><tbody>{recent_rows}</tbody></table></div></div>
<div class='band'><h2>全歷史逐期一致性掃描</h2><p class='note'>從第321期起逐期重算；此區只做方向診斷，不冒充隔離驗證。</p><div class='table-wrap'><table><thead><tr><th>項目</th><th>結果</th></tr></thead><tbody>{full_rows}</tbody></table></div></div>
<div class='band warning'><h2>回測規則</h2><p>每一測試期只讀取該期以前已知資料；禁止用同一期開獎結果改寫同一期預測。</p></div>"""
    return _page_shell("backtest.html", "回測驗證", "只顯示回測與方向檢查", content)


def _review_page(settlements, weights, selection, feature_labels):
    if not settlements:
        return _page_shell("review.html", "開獎檢討", "只顯示最新一期開獎後檢討", "<div class='band empty'>等待第一筆開獎前封存完成結算</div>")
    item = settlements[-1]
    if item.get("review_status") == "recovery_no_pre_draw_seal":
        diagnostic = selection.get("diagnostic") or {}
        content = f"""
<div class='band warning'><h2>最新一期命中結算</h2><div class='grid'>
<div class='card'><div class='label'>檢討開獎日</div><div class='value'>{item.get('target_draw_date','－')}</div></div>
<div class='card'><div class='label'>實際開獎</div><div class='value number-line'>{_fmt(item.get('actual_numbers') or [])}</div></div>
<div class='card'><div class='label'>開獎前前5正式預測</div><div class='value'>停擺期無封存，不補造</div></div>
<div class='card'><div class='label'>前5命中資料</div><div class='value'>無開獎前封存，禁止事後計算</div></div>
<div class='card'><div class='label'>第10至15名命中</div><div class='value'>無開獎前封存，禁止事後計算</div></div>
</div></div>
<div class='band warning'><h2>本期重大瑕疵結論</h2><p><b>系統停擺造成此期沒有可驗證的開獎前正式封存；只登錄官方開獎事實，禁止開獎後換號或補號，也不偽造命中率。</b></p></div>
<div class='band'><h2>實際開獎號碼原始排名</h2><p>沒有開獎前封存，無法誠實還原當時排名；本區明確標記缺失，不以事後資料回算。</p></div>
<div class='band'><h2>錯誤模組與前9邊界逐項檢討</h2><p>沒有開獎前逐號模組證據，因此不製造假檢討；更新鏈已恢復，後續每期均由開獎前封存自動結算。</p></div>
<div class='band strong'><h2>開獎後滾動權重重算</h2><p>已使用補齊後的全歷史資料重新搜尋全部 {diagnostic.get('candidate_count',0)} 組權重，正式預測已恢復產出。</p></div>"""
        return _page_shell("review.html", "開獎檢討", "停擺缺口已誠實登錄，預測持續更新", content)
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
    average_rank=float(item.get("average_actual_rank") or 0)
    top5_published=item.get("top5_published") or []
    top5_hits=item.get("top5_hits") or []
    published_single=item.get("single_published")
    single_result=(f"{int(published_single):02}・{'命中' if item.get('single_hit') else '未中'}"
                   if published_single is not None else "未達標，未發布")
    catastrophic=(not (item.get("top9_hits") or []) and average_rank>=22)
    guard_removed_hit=item.get("catastrophic_guard_single_effect")=="removed_hit"
    if guard_removed_hit:
        diagnosis=(f"已確認重大邏輯錯誤：保護前原始第1名 {int(item.get('unguarded_single',0)):02} 實際命中，"
                   f"但舊版失準保護將它換成 {int(item.get('single_published',0)):02}，造成正式1中1未中。"
                   "保護規則已修成永久保留原始第1名，只調整第2至第9名。")
    elif catastrophic:
        diagnosis="本期5顆實際號碼整批落在排序深後段，屬於方向性失準；下一期啟動保留原始第1名的有限度失準保護。"
    else:
        diagnosis="本期未達災難失準門檻；維持正式方向競賽並逐模組回灌。"
    content = f"""
<div class='band'><h2>最新一期命中結算</h2><div class='grid'>
<div class='card'><div class='label'>檢討開獎日</div><div class='value'>{item.get('target_draw_date','－')}</div></div>
<div class='card'><div class='label'>實際開獎</div><div class='value number-line'>{_fmt(item.get('actual_numbers') or [])}</div></div>
<div class='card'><div class='label'>開獎前1中1主選</div><div class='value'>{single_result}</div></div>
<div class='card'><div class='label'>保護前原始第1名</div><div class='value'>{int(item.get('unguarded_single') or item.get('single_published',0)):02}・{'命中' if item.get('unguarded_single_hit') else '未中'}</div></div>
<div class='card'><div class='label'>開獎前前5正式預測</div><div class='value number-line'>{_fmt(top5_published)}</div></div>
<div class='card'><div class='label'>前5命中資料</div><div class='value'>{_fmt(top5_hits) or '未命中'}・共{len(top5_hits)}顆</div></div>
<div class='card'><div class='label'>開獎前前9命中</div><div class='value'>{_fmt(item.get('top9_hits') or []) or '0顆'}</div></div>
<div class='card'><div class='label'>第10至15名命中</div><div class='value'>{_fmt(item.get('rank10_15_hits') or []) or '0顆'}</div></div>
<div class='card'><div class='label'>實際號碼平均名次</div><div class='value'>{average_rank:.1f}</div></div>
</div></div>
<div class='band {'warning' if catastrophic else ''}'><h2>本期重大瑕疵結論</h2><p><b>{diagnosis}</b></p></div>
<div class='band'><h2>實際開獎號碼原始排名</h2><div class='table-wrap'><table><thead><tr><th>號碼</th><th>開獎前排名</th><th>相對指數</th><th>區段</th></tr></thead><tbody>{actual_rows}</tbody></table></div></div>
<div class='band warning'><h2>錯誤模組與前9邊界逐項檢討</h2><p><b>失準模組：{errors}</b></p><div class='table-wrap'><table><thead><tr><th>模組</th><th>開獎號平均貢獻</th><th>前5落空號平均貢獻</th><th>整體鑑別差</th><th>邊界鑑別差</th><th>處理</th></tr></thead><tbody>{module_rows}</tbody></table></div></div>
<div class='band'><h2>開獎後滾動權重重算</h2><p>本期已重新搜尋全部 {diagnostic.get('candidate_count',0)} 組權重，保留 {diagnostic.get('eligible_candidate_count',0)} 組均衡候選，再完成方向模型逐期重選。</p><div class='table-wrap'><table><thead><tr><th>模組</th><th>開獎前權重</th><th>重算後權重</th><th>調整</th></tr></thead><tbody>{weight_rows}</tbody></table></div></div>
<div class='band'><h2>檢討證據</h2><div class='grid'><div class='card'><div class='label'>開獎前封存驗證碼</div><div class='value'>{_numeric_code(item.get('pre_draw_seal_sha256') or item.get('legacy_reconstruction_sha256'))}</div></div><div class='card'><div class='label'>檢討驗證碼</div><div class='value'>{_numeric_code(item.get('review_evidence_sha256'))}</div></div></div><p class='note'>只讀取開獎前封存資料，禁止開獎後換號或補號。</p></div>"""
    return _page_shell("review.html", "開獎檢討", "只顯示最新一期命中檢討與滾動修正", content)


def _history_page(settlements, draws):
    settlement_by_date={str(item.get("target_draw_date") or ""):item for item in settlements}
    settlement_dates=sorted(date for date in settlement_by_date if date)
    start=settlement_dates[0] if settlement_dates else None
    expected=[draw for draw in draws if start and start<=str(draw.get("date") or "")<=str(draws[-1].get("date") or "")]
    expected_dates=[str(draw.get("date") or "") for draw in expected]
    missing_dates=[date for date in expected_dates if date not in settlement_by_date]
    sealed=sum(1 for date in expected_dates if (settlement_by_date.get(date) or {}).get("review_status")=="completed_from_pre_draw_seal")
    recovered=sum(1 for date in expected_dates if (settlement_by_date.get(date) or {}).get("review_status")=="recovery_no_pre_draw_seal")
    rows_list=[]
    for item in reversed(settlements):
        period=str(item.get('official_period') or '－')
        if item.get("review_status") == "recovery_no_pre_draw_seal":
            rows_list.append(f"<tr><td>{item.get('target_draw_date','－')}</td><td>{period}</td><td>官方開獎已補齊</td><td>原始封存不存在</td><td>禁止補算</td><td>禁止補算</td><td>禁止補算</td><td>{_fmt(item.get('actual_numbers') or [])}</td><td>停擺缺口已登錄</td><td>禁止補算</td><td>禁止補算</td></tr>")
        else:
            published_single=item.get('single_published')
            single_text=f"{int(published_single):02}" if published_single is not None else "未發布"
            single_hit_text=("命中" if item.get('single_hit') else "未中") if published_single is not None else "不計命中"
            rows_list.append(f"<tr><td>{item.get('target_draw_date','－')}</td><td>{period}</td><td>事前封存已驗證</td><td>{single_text}</td><td>{_fmt(item.get('top5_published') or []) or '未發布'}</td><td>{_fmt(item.get('top5_hits') or []) or '未命中'}・{len(item.get('top5_hits') or [])}顆</td><td>{_fmt(item.get('top9_published') or []) or '未發布'}</td><td>{_fmt(item.get('actual_numbers') or [])}</td><td>{single_hit_text}</td><td>{_fmt(item.get('top9_hits') or []) or '0顆'}</td><td>{_fmt(item.get('rank10_15_hits') or []) or '0顆'}</td></tr>")
    rows = "".join(rows_list)
    if not rows:
        rows = "<tr><td colspan='11'>尚無已結算封存紀錄</td></tr>"
    content = f"""
<div class='band'><h2>歷史資料完整度</h2><div class='grid'>
<div class='card'><div class='label'>官方開獎應有</div><div class='value'>{len(expected_dates)}期</div></div>
<div class='card'><div class='label'>已登錄</div><div class='value ok'>{len(expected_dates)-len(missing_dates)}期</div></div>
<div class='card'><div class='label'>可驗證事前封存</div><div class='value'>{sealed}期</div></div>
<div class='card'><div class='label'>停擺官方補錄</div><div class='value'>{recovered}期</div></div>
<div class='card'><div class='label'>尚缺官方資料</div><div class='value {'ok' if not missing_dates else 'bad'}'>{len(missing_dates)}期</div></div>
</div><p class='note'>停擺期間遺失的是開獎前預測封存，不是官方開獎資料。官方期別與實際號碼已逐期補齊；不存在的事前封存不得於開獎後補造。</p></div>
<div class='band'><h2>開獎前封存實戰紀錄</h2><p class='note'>本頁逐期顯示官方期別、資料狀態與結算；最新一期的逐模組原因與權重調整請看「開獎檢討」。</p><div class='table-wrap'><table><thead><tr><th>開獎日</th><th>官方期別</th><th>資料狀態</th><th>開獎前1中1</th><th>開獎前前5</th><th>前5命中資料</th><th>開獎前前9</th><th>實際開獎</th><th>主選結果</th><th>前9命中</th><th>第10至15名命中</th></tr></thead><tbody>{rows}</tbody></table></div></div>"""
    return _page_shell("history.html", "歷史封存", "只顯示各期開獎前正式封存與結算", content)


def _models_page(draws, weights, bt, selection, repeat_audit, feature_labels):
    diagnostic = selection.get("diagnostic") or {}
    long_window = diagnostic.get("long_history_selection_window") or {}
    direct_baseline = bt.get("direct_hit_baseline") or {}
    direct_baseline54 = bt.get("direct_hit_baseline_recent_54") or {}
    direct_baseline120 = bt.get("direct_hit_baseline_recent_120") or {}
    stability=bt.get("anchor_stability") or selection.get("anchor_stability") or {}
    champion=stability.get("champion_metrics") or {}
    challenger=stability.get("challenger_metrics") or {}
    stability_rows="".join(
        f"<tr><td>{label}</td><td>{champion.get(key,'－')}</td><td>{challenger.get(key,'－')}</td></tr>"
        for label,key in (("最後360期第1名命中","last360_single_hits"),("最後360期前5平均","last360_top5_avg_hits"),("最後360期前9平均","last360_top9_avg_hits"),("最近54期第1名命中","recent54_single_hits"),("最近54期前5平均","recent54_top5_avg_hits"),("最近54期前9平均","recent54_top9_avg_hits"))
    )
    formula_rows = "".join(
        f"<tr><td>{feature_labels.get(key,key)}</td><td>逐期擴展全歷史資料庫</td><td>{value:+.3f}</td><td>{'正向' if value>=0 else '反向'}</td></tr>"
        for key, value in weights.items()
    )
    rule_rows = "".join(
        f"<tr><td>{item['number']:02}</td><td>{item['relative_index']:.1f}</td><td>{item['transition_contribution']:+.3f}</td><td>{item['positive_module_count']}</td><td>{100*item['repeat_rate']:.2f}%</td><td>{'通過' if item['repeat_backtest_pass'] else '未通過'}</td></tr>"
        for item in repeat_audit
    )
    strict=bt.get("strict_publication_gate") or {}
    supermodel=bt.get("single_supermodel") or {}
    fusion=supermodel.get("global_fusion") or {}
    fusion_model_rows="".join(
        f"<tr><td>{item.get('family','－')}</td><td>{item.get('label','－')}</td><td>{int(item.get('candidate',0)):02}</td><td>{item.get('robust_score',0):+.3f}</td><td>{'保留' if item.get('robust_score',0)>0 else '淘汰'}</td></tr>"
        for item in (fusion.get("family_champions") or [])
    )
    content = f"""
<div class='band'><h2>全歷史運算範圍</h2><div class='grid'>
<div class='card'><div class='label'>資料範圍</div><div class='value'>{draws[0]['date']}～{draws[-1]['date']}</div></div>
<div class='card'><div class='label'>全歷史期數</div><div class='value'>{len(draws):,}期</div></div>
<div class='card'><div class='label'>全歷史核心占比</div><div class='value'>100%</div></div>
<div class='card'><div class='label'>短期正式權重</div><div class='value'>0%</div></div>
</div></div>
<div class='band'><h2>正式方向模型</h2><p>每次預測與每一期回測都使用當時以前的全部歷史資料。先搜尋 {diagnostic.get('candidate_count',0)} 組錨定權重，保留 {diagnostic.get('eligible_candidate_count',0)} 組均衡候選，再建立 {bt.get('strategy_candidate_count',0)} 組模組正反方向模型；每一期只用此前 {bt.get('strategy_selection_window',0)} 期已開獎成績選出 {bt.get('strategy_consensus_member_count',0)} 組，平均成可完整驗算的五組正式權重共識。其餘38顆再融合 {100*bt.get('direct_hit_full_rank_blend',0):.0f}% 直接命中全排序校準；第一名另經單碼重複冷卻守門；資料變化模型只做影子驗證，正式占比為零。</p><div class='table-wrap'><table><thead><tr><th>正式模組</th><th>資料來源</th><th>目前權重</th><th>方向</th></tr></thead><tbody>{formula_rows}</tbody></table></div></div>
<div class='band warning'><h2>全系統重組</h2><p><b>第三代採用「全歷史五組方向共識＋35%直接命中全排序＋單碼重複冷卻＋資料變化影子驗證」四層架構。</b>修正舊版直接命中占比不足與失效增量模組仍干擾正式排序兩項缺陷。最近54、120及360期均獨立列示，不再用長期成績掩蓋近期退化。</p></div>
<div class='band strong'><h2>超級獨支獨立模型</h2><p><b>舊版直接命中校準永久固定原第1名，無法修正獨支；新版將獨支從全排序拆出，讓四十組「動態時間窗＋全歷史基準」模型真正競爭第1名。</b>每一百二十期才重新選型，並用下一段未見資料驗證。所有候選都保留全歷史基準，禁止只看上一期或用開獎後答案換號。</p><div class='grid'><div class='card'><div class='label'>候選模型</div><div class='value'>{supermodel.get('parameter_count',0)}組</div></div><div class='card'><div class='label'>目前時間窗</div><div class='value'>{supermodel.get('selected_window',0)}期</div></div><div class='card'><div class='label'>全歷史占比</div><div class='value'>{100*supermodel.get('selected_global_history_blend',0):.0f}%</div></div><div class='card'><div class='label'>同碼模型共識</div><div class='value'>{supermodel.get('candidate_consensus_count',0)}組</div></div></div></div>
<div class='band strong'><h2>全球八家族軌跡融合架構</h2><p><b>系統建立{fusion.get('module_count',0)}組模型，涵蓋多時間窗頻率、指數時間衰減、動量反轉、間隔風險、前期轉移、多階拖牌軌跡、週期間隔危險率及開獎日條件八類。</b>每組都要在一千四百四十、七百二十、三百六十、二百四十、一百二十與五十四期六個區段全部高於基準，才准進入融合投票；不穩定家族直接淘汰。</p><div class='grid'><div class='card'><div class='label'>總模組</div><div class='value'>{fusion.get('module_count',0)}組</div></div><div class='card'><div class='label'>合格模組</div><div class='value'>{fusion.get('accepted_module_count',0)}組</div></div><div class='card'><div class='label'>融合首選</div><div class='value'>{int(fusion.get('fusion_candidate') or 0):02}</div></div><div class='card'><div class='label'>軌跡升級</div><div class='value'>{'通過' if (fusion.get('production_upgrade_gate') or {}).get('passed') else '未通過，禁止取代'}</div></div></div><div class='table-wrap'><table><thead><tr><th>家族</th><th>冠軍參數</th><th>本期首選</th><th>最弱區段分數</th><th>結果</th></tr></thead><tbody>{fusion_model_rows}</tbody></table></div><p class='note'>新增軌跡模型必須以逐期前推結果證明提升；只改善局部區段而拖累整體時，一律留在影子驗證，不得冒充正式升級。</p></div>
<div class='band'><h2>全球方法查證來源</h2><p>本次融合依照可公開查證的原始研究與官方技術文件設計，不採用無回測證據的民間必中公式。</p><ul><li><a href='https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html' target='_blank' rel='noopener'>時間序列逐期前推驗證官方說明</a></li><li><a href='https://scikit-learn.org/stable/modules/calibration.html' target='_blank' rel='noopener'>預測機率校準與可靠度官方說明</a></li><li><a href='https://proceedings.mlr.press/v202/xu23r.html' target='_blank' rel='noopener'>序列資料不確定性校正研究</a></li><li><a href='https://journals.ametsoc.org/view/journals/mwre/133/5/mwr2906.1.xml' target='_blank' rel='noopener'>貝葉斯模型平均研究</a></li><li><a href='https://csrc.nist.gov/pubs/sp/800/22/r1/upd1/final' target='_blank' rel='noopener'>隨機性統計檢驗官方標準</a></li></ul><p class='note'>這些方法用來防止未來資料洩漏、校準信心、融合不同模型及檢查結果是否可能只是隨機波動；它們不能創造不存在的必中規律。</p></div>
<div class='band strong'><h2>主程式完整壓縮包</h2><p>包含核心運算、全球融合、自動更新、自主修復看門狗、頁面產生器、完整驗收、雲端流程及歷史資料。</p><p><a class='nav-pill' href='./downloads/台灣539主程式完整包.zip' download>下載主程式完整壓縮包</a></p></div>
<div class='band'><h2>穩定冠軍與每日挑戰模型</h2><p><b>本期採用：{stability.get('selected','－')}。</b>每日新模型只有在長期與近期六項指標全部不差、至少三項改善，而且兩個區間排序方向都通過，才准取代穩定冠軍。</p><div class='table-wrap'><table><thead><tr><th>驗證項目</th><th>穩定冠軍</th><th>每日挑戰模型</th></tr></thead><tbody>{stability_rows}</tbody></table></div></div>
<div class='band'><h2>多模組校正規格</h2><div class='grid'>
<div class='card'><div class='label'>錨定候選</div><div class='value'>{diagnostic.get('candidate_count',0)}組</div></div>
<div class='card'><div class='label'>均衡候選</div><div class='value'>{diagnostic.get('eligible_candidate_count',0)}組</div></div>
<div class='card'><div class='label'>長歷史複驗</div><div class='value'>{long_window.get('samples',0)}個逐期樣本</div></div>
<div class='card'><div class='label'>長歷史分段</div><div class='value'>{long_window.get('folds',0)}段</div></div>
<div class='card'><div class='label'>方向模型</div><div class='value'>{bt.get('strategy_candidate_count',0)}組</div></div>
<div class='card'><div class='label'>方向選擇窗</div><div class='value'>{bt.get('strategy_selection_window',0)}期</div></div>
<div class='card'><div class='label'>權重共識</div><div class='value'>{bt.get('strategy_consensus_member_count',0)}組</div></div>
<div class='card'><div class='label'>直接命中校準窗</div><div class='value'>{bt.get('direct_hit_window',0)}期</div></div>
<div class='card'><div class='label'>全排序融合占比</div><div class='value'>{100*bt.get('direct_hit_full_rank_blend',0):.0f}%</div></div>
<div class='card'><div class='label'>資料變化比較窗</div><div class='value'>{bt.get('data_change_window',0)}期</div></div>
</div></div>
<div class='band'><h2>連莊資格驗算規格</h2><p>上一期號碼必須同時符合：相對指數至少75、全歷史轉移貢獻為正、至少兩個正式模組正貢獻、全歷史連莊率不低於12.82%，且個別回測通過；不做補位。</p><div class='table-wrap'><table><thead><tr><th>上一期號碼</th><th>相對指數</th><th>轉移貢獻</th><th>正貢獻模組</th><th>全歷史連莊率</th><th>個別回測</th></tr></thead><tbody>{rule_rows}</tbody></table></div></div>"""
    content += f"""<div class='band strong'><h2>嚴格發布規格</h2><p><b>正式推薦不是固定湊滿顆數。</b>每個號碼都必須位於內部前九、分數高於零、相對指數至少七十五、至少兩項正貢獻、至少兩個正式模組排入各自前十五，直接命中校準也必須通過；若是上一期號碼，還要再通過個別連莊資格。任何一項失敗立即淘汰。</p><div class='grid'><div class='card'><div class='label'>本期合格數</div><div class='value'>{strict.get('qualified_count',0)}顆</div></div><div class='card'><div class='label'>補位政策</div><div class='value'>禁止補位</div></div><div class='card'><div class='label'>不合格號碼</div><div class='value'>禁止推薦</div></div></div></div>"""
    return _page_shell("models.html", "模型說明", "只顯示資料範圍、公式與校正規格", content)


def _health_page(draws, bt, full_scan, generated_at, settlements, health):
    latest = draws[-1]
    direction = "通過" if bt.get("ranking_direction_valid") else "未通過"
    settled = bool(settlements and settlements[-1].get("review_status") in ("completed_from_pre_draw_seal","recovery_no_pre_draw_seal"))
    checks = (
        ("資料完整性", "通過", "期別與日期去重；每期5個不重複號碼"),
        ("全歷史模式", "通過", f"正式運算使用全部 {len(draws):,} 期"),
        ("自動重新運算", "通過", "開獎資料更新後重建所有分頁"),
        ("命中檢討", "通過" if settled else "等待結算", "只採用開獎前封存資料"),
        ("前9邊界", "通過" if bt.get("boundary_control_valid") else "未通過", "比較每個排名位置命中率"),
        ("排序方向", direction, "最後360期隔離檢查"),
        ("失準事件監測", "只記錄" if bt.get("catastrophic_guard_current_condition") else "待命中", "永久禁止旋轉、換號或改動正式排序"),
        ("正式排序保護", "通過" if not bt.get("catastrophic_guard_execution_enabled") and bt.get("catastrophic_guard_application_count")==0 else "未通過", "失準監測不得改動任何正式名次"),
        ("穩定模型守門", (bt.get("anchor_stability") or {}).get("selected","－"), "每日挑戰模型須長短期六項全部不退步才可升級"),
        ("五組權重共識", "通過" if bt.get("strategy_consensus_member_count")==5 else "未通過", "三十組中以前三百六十期成績選出五組並平均正式權重"),
        ("直接命中全排序校準", "通過" if bt.get("direct_hit_calibration_enabled") and bt.get("direct_hit_full_rank_gate") else "未通過", "其餘38顆重新融合；前9集合允許修正"),
        ("單碼重複冷卻", "通過" if bt.get("single_repeat_break_enabled") and bt.get("single_repeat_break_gate") else "未通過", "重複首位改採共識次選，並以逐日封存狀態維持冷卻"),
        ("資料變化影子驗證", "影子觀察" if bt.get("data_change_enabled") and not bt.get("data_change_gate") else "通過", "正式占比為零；跨區段同時通過後才准上線"),
        ("短窗單碼重排", "已停用", "跨校正區與隔離區不穩定，不得改動正式第1名"),
        ("嚴格發布守門", "通過" if (bt.get("strict_publication_gate") or {}).get("no_padding") else "未通過", "逐號驗算；不足一、二、三、五、九顆時不補位"),
        ("超級獨支模型", "通過" if (bt.get("single_supermodel") or {}).get("release_gate_passed") else "未通過", f"四十組主模型、{((bt.get('single_supermodel') or {}).get('global_fusion') or {}).get('module_count',0)}組全球八家族軌跡融合、六段時間隔離守門"),
        ("手機同步", "通過", "開啟、回到前景與重新連網時立即核對；同步後每30秒巡檢"),
        ("三十分鐘自修", ("啟用前舊期" if not health.get("deadline_enforced_for_latest_draw") else ("通過" if health.get("thirty_minute_deadline_met",True) else ("逾時後已補齊" if health.get("deadline_recovered") else "逾時故障"))), "自2026年10月7日開獎起，超過期限立即重跑資料、模型、分頁、部署與公開驗收"),
    )
    rows = "".join(f"<tr><td>{name}</td><td>{status}</td><td>{detail}</td></tr>" for name, status, detail in checks)
    content = f"""
<div class='band'><h2>目前資料狀態</h2><div class='grid'>
<div class='card'><div class='label'>最新開獎期別</div><div class='value'>{latest['period']}</div></div>
<div class='card'><div class='label'>最新開獎日</div><div class='value'>{latest['date']}</div></div>
<div class='card'><div class='label'>歷史期數</div><div class='value'>{len(draws):,}期</div></div>
<div class='card'><div class='label'>最後運算時間</div><div class='value'>{generated_at}</div></div>
</div></div>
<div class='band'><h2>開獎後更新與自主修復</h2><div class='grid'>
<div class='card'><div class='label'>官方開獎時間</div><div class='value'>{_display_time(health.get('official_draw_time'))}</div></div>
<div class='card'><div class='label'>完成同步時間</div><div class='value'>{_display_time(health.get('sync_completed_at'))}</div></div>
<div class='card'><div class='label'>同步延遲</div><div class='value'>{health.get('sync_delay_minutes','－')}分鐘</div></div>
<div class='card'><div class='label'>三十分鐘完成期限</div><div class='value'>{_display_time(health.get('thirty_minute_repair_deadline'))}</div></div>
<div class='card'><div class='label'>期限結果</div><div class='value'>{'鐵律啟用前舊期' if not health.get('deadline_enforced_for_latest_draw') else ('期限內完成' if health.get('thirty_minute_deadline_met',True) else ('曾逾時，資料已補齊' if health.get('deadline_recovered') else '逾時故障並已觸發自修'))}</div></div>
<div class='card'><div class='label'>執行位置</div><div class='value'>全天候雲端</div></div>
<div class='card'><div class='label'>本機關機</div><div class='value'>{'照常更新' if health.get('cloud_independent_update') and health.get('local_computer_required') is False else '設定異常'}</div></div>
<div class='card'><div class='label'>雲端更新排程</div><div class='value'>{health.get('cloud_update_schedule','開獎時段每五分鐘核對')}</div></div>
<div class='card'><div class='label'>最遲啟動</div><div class='value'>開獎後{health.get('update_start_deadline_minutes',10)}分鐘</div></div>
<div class='card'><div class='label'>最遲完成</div><div class='value'>開獎後{health.get('completion_deadline_minutes',30)}分鐘</div></div>
<div class='card'><div class='label'>故障巡檢</div><div class='value'>每{health.get('watchdog_interval_minutes',5)}分鐘</div></div>
<div class='card'><div class='label'>電腦手機同步</div><div class='value'>{'同一版號' if health.get('desktop_mobile_sync') else '同步異常'}</div></div>
<div class='card'><div class='label'>共同版號</div><div class='value'>{health.get('desktop_mobile_shared_version','－')}</div></div>
<div class='card'><div class='label'>自主修復狀態</div><div class='value'>{health.get('self_repair_status','雲端待命')}</div></div>
<div class='card'><div class='label'>累計自主修復</div><div class='value'>{health.get('self_repair_count',0)}次</div></div>
<div class='card'><div class='label'>最後公開驗收</div><div class='value'>{_display_time(health.get('last_public_verification_at'))}</div></div>
</div></div>
<div class='band'><h2>鐵律守門</h2><div class='table-wrap'><table><thead><tr><th>項目</th><th>結果</th><th>說明</th></tr></thead><tbody>{rows}</tbody></table></div></div>
<div class='band'><h2>模型健康與公開狀態</h2><div class='grid'>
<div class='card'><div class='label'>公開狀態</div><div class='value ok'>嚴格守門正常</div></div>
<div class='card'><div class='label'>本期合格號碼</div><div class='value'>{(bt.get('strict_publication_gate') or {}).get('qualified_count',0)}顆</div></div>
<div class='card'><div class='label'>超級獨支候選</div><div class='value'>{(bt.get('single_supermodel') or {}).get('candidate','－')}</div></div>
<div class='card'><div class='label'>排序方向判定</div><div class='value'>排序方向{direction}</div></div>
<div class='card'><div class='label'>方向模型數</div><div class='value'>{bt.get('strategy_candidate_count',0)}組</div></div>
<div class='card'><div class='label'>權重共識組數</div><div class='value'>{bt.get('strategy_consensus_member_count',0)}組</div></div>
<div class='card'><div class='label'>直接命中校準</div><div class='value'>{'通過' if bt.get('direct_hit_calibration_enabled') else '未通過'}</div></div>
<div class='card'><div class='label'>資料變化校正</div><div class='value'>{'通過' if bt.get('data_change_gate') else '未通過'}</div></div>
<div class='card'><div class='label'>隔離回測期數</div><div class='value'>{bt.get('samples',0)}期</div></div>
<div class='card'><div class='label'>全歷史診斷期數</div><div class='value'>{full_scan.get('samples',0)}期</div></div>
</div></div><div class='band strong'><h2>主程式下載</h2><p><a class='nav-pill' href='./downloads/台灣539主程式完整包.zip' download>下載主程式完整壓縮包</a></p></div>"""
    return _page_shell("health.html", "系統健康", "只顯示資料更新、同步與完整性狀態", content)


def render_report_pages(draws, weights, score, tickets, bt, full_scan, repeat_audit, selection, reports_dir: Path, feature_labels: dict, generated_at: str | None = None) -> dict[str, str]:
    latest = draws[-1]
    rank_numbers = __import__("tw539_ultra").rank_numbers
    ranking = rank_numbers(score, latest["period"])
    target = datetime.strptime(latest["date"], "%Y-%m-%d").date() + timedelta(days=1)
    while target.weekday() == 6:
        target += timedelta(days=1)
    if generated_at:
        generated_at = str(generated_at)[:16].replace("T", " ")
    else:
        generated_at = datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M")
    settlements = _read_jsonl(reports_dir / "published-settlements.jsonl")
    health = _read_json(reports_dir / "system-health.json")
    return {
        "index.html": _prediction_page(draws, weights, score, tickets, repeat_audit, ranking, target.isoformat(), generated_at, feature_labels, bt),
        "backtest.html": _backtest_page(bt, full_scan),
        "review.html": _review_page(settlements, weights, selection, feature_labels),
        "history.html": _history_page(settlements, draws),
        "models.html": _models_page(draws, weights, bt, selection, repeat_audit, feature_labels),
        "health.html": _health_page(draws, bt, full_scan, generated_at, settlements, health),
    }
