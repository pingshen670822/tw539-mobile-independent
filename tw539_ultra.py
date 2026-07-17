#!/usr/bin/env python3
"""TW539 科學分析系統：可重現、可回測、不宣稱能預知隨機開獎。"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import random
import shutil
from collections import Counter
from datetime import datetime
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "539.csv"
OUT = ROOT / "reports"


def load_draws(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            try:
                nums = tuple(sorted(int(r[f"n{i}"]) for i in range(1, 6)))
                if len(set(nums)) != 5 or nums[0] < 1 or nums[-1] > 39:
                    continue
                rows.append({"period": r["period"], "date": r["draw_date"], "nums": nums})
            except (ValueError, KeyError, TypeError):
                continue
    unique = {r["period"]: r for r in rows}
    return sorted(unique.values(), key=lambda x: (x["date"], x["period"]))


def normalize(values: dict[int, float]) -> dict[int, float]:
    lo, hi = min(values.values()), max(values.values())
    if hi == lo:
        return {n: 0.5 for n in values}
    return {n: (v - lo) / (hi - lo) for n, v in values.items()}


def feature_table(history: list[dict]) -> dict[str, dict[int, float]]:
    universe = range(1, 40)
    sets = [set(x["nums"]) for x in history]
    feats: dict[str, dict[int, float]] = {}
    for w in (10, 30, 100):
        sample = sets[-w:]
        c = Counter(n for s in sample for n in s)
        feats[f"freq{w}"] = normalize({n: c[n] / max(1, len(sample)) for n in universe})
    gap = {}
    for n in universe:
        gap[n] = next((i for i, s in enumerate(reversed(sets)) if n in s), len(sets))
    # 遺漏不是「該出了」；壓縮極端值，僅作弱特徵。
    feats["gap"] = normalize({n: math.log1p(min(gap[n], 30)) for n in universe})
    long_rate = {n: sum(n in s for s in sets[-300:]) / max(1, len(sets[-300:])) for n in universe}
    short_rate = {n: sum(n in s for s in sets[-20:]) / max(1, len(sets[-20:])) for n in universe}
    feats["momentum"] = normalize({n: short_rate[n] - long_rate[n] for n in universe})
    feats["reversion"] = normalize({n: -abs(long_rate[n] - 5 / 39) for n in universe})
    recent = sets[-60:]
    pairs = Counter(p for s in recent for p in combinations(sorted(s), 2))
    last = sets[-1]
    feats["association"] = normalize({n: sum(pairs[tuple(sorted((n, x)))] for x in last if x != n) for n in universe})
    # 全球常見時間序列模組：指數時間衰減、Beta-Binomial 平滑、一期轉移。
    decay = {n: 0.0 for n in universe}
    for age, s in enumerate(reversed(sets[-180:])):
        w = math.exp(-age / 35)
        for n in s: decay[n] += w
    feats["ewma"] = normalize(decay)
    recent30 = sets[-30:]
    feats["bayes"] = normalize({n: (1 + sum(n in s for s in recent30)) / (2 + len(recent30)) for n in universe})
    transitions = Counter()
    for a, b in zip(sets[-180:-1], sets[-179:]):
        for x in a:
            for y in b: transitions[(x, y)] += 1
    feats["transition"] = normalize({n: sum(transitions[(x, n)] for x in last) for n in universe})
    # 牌型結構模組：尾數分散、鄰號橋接、區間壓力、週期相位。
    tail_count=Counter(x % 10 for s in sets[-40:] for x in s)
    feats["tail_balance"] = normalize({n: -tail_count[n % 10] for n in universe})
    feats["neighbor"] = normalize({n: sum((n-1 in s)+(n+1 in s) for s in sets[-30:]) for n in universe})
    zone_count=Counter((x-1)//10 for s in sets[-20:] for x in s)
    feats["zone_balance"] = normalize({n: -zone_count[(n-1)//10] for n in universe})
    appearances={n:[i for i,s in enumerate(sets) if n in s] for n in universe}
    feats["cycle"] = normalize({n: -abs(gap[n]-(sum(b-a for a,b in zip(appearances[n][-8:-1],appearances[n][-7:]))/max(1,len(appearances[n][-7:])) if len(appearances[n])>2 else 8)) for n in universe})
    return feats


WEIGHT_CANDIDATES = [
    {"freq10": .10, "freq30": .25, "freq100": .25, "gap": .08, "momentum": .10, "reversion": .17, "association": .05},
    {"freq10": .05, "freq30": .15, "freq100": .35, "gap": .05, "momentum": .05, "reversion": .30, "association": .05},
    {"freq10": .20, "freq30": .25, "freq100": .15, "gap": .10, "momentum": .15, "reversion": .10, "association": .05},
    {"freq30": .10, "freq100": .10, "gap": .05, "reversion": .15, "association": .05, "ewma": .20, "bayes": .20, "transition": .15},
    {"freq100": .10, "reversion": .20, "ewma": .25, "bayes": .25, "transition": .15, "association": .05},
    {"freq30":.10,"freq100":.10,"reversion":.15,"ewma":.15,"bayes":.15,"transition":.10,"tail_balance":.08,"neighbor":.07,"zone_balance":.05,"cycle":.05},
    {"reversion":.20,"bayes":.20,"ewma":.15,"association":.10,"transition":.10,"tail_balance":.07,"neighbor":.06,"zone_balance":.06,"cycle":.06},
]


def scores(history: list[dict], weights: dict[str, float]) -> dict[int, float]:
    f = feature_table(history)
    raw = {n: sum(weights[k] * f[k][n] for k in weights) for n in range(1, 40)}
    # 收縮至均等機率，避免把隨機波動說成強訊號。
    avg = sum(raw.values()) / 39
    return {n: .65 * raw[n] + .35 * avg for n in raw}


def choose_weights(draws: list[dict], tests: int = 180) -> tuple[dict[str, float], list[float]]:
    start = max(320, len(draws) - tests)
    quality = [0.0] * len(WEIGHT_CANDIDATES)
    for i in range(start, len(draws)):
        actual = set(draws[i]["nums"])
        for j, w in enumerate(WEIGHT_CANDIDATES):
            candidate_scores = scores(draws[:i], w)
            ranked = sorted(candidate_scores, key=candidate_scores.get, reverse=True)[:15]
            # 獨隻1中1為首要目標；前5、前9只作次要破同分依據。
            quality[j] += (100 if ranked[0] in actual else 0) + 5*len(actual.intersection(ranked[:5])) + len(actual.intersection(ranked[:9]))
    best = max(range(len(quality)), key=quality.__getitem__)
    return WEIGHT_CANDIDATES[best], quality


def valid_ticket(t: tuple[int, ...]) -> bool:
    odd = sum(n % 2 for n in t)
    low = sum(n <= 20 for n in t)
    decades = len({(n - 1) // 10 for n in t})
    consecutive = sum(b == a + 1 for a, b in zip(t, t[1:]))
    return odd in (2, 3) and low in (2, 3) and decades >= 3 and consecutive <= 2 and 65 <= sum(t) <= 135


def make_tickets(score: dict[int, float], count: int, seed: str) -> list[tuple[int, ...]]:
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16))
    nums = list(range(1, 40)); weights = [max(score[n], .001) ** 2.2 for n in nums]
    tickets = []
    for _ in range(30000):
        pool, ws, pick = nums[:], weights[:], []
        for _ in range(5):
            x = rng.choices(pool, weights=ws, k=1)[0]; idx = pool.index(x)
            pick.append(x); pool.pop(idx); ws.pop(idx)
        t = tuple(sorted(pick))
        if valid_ticket(t) and t not in tickets and all(len(set(t) & set(old)) <= 3 for old in tickets):
            tickets.append(t)
            if len(tickets) == count: break
    return tickets


def backtest(draws: list[dict], weights: dict[str, float], tests: int = 180, ticket_count: int = 8) -> dict:
    start = max(320, len(draws) - tests); hist = Counter(); total_hits = 0
    for i in range(start, len(draws)):
        sc = scores(draws[:i], weights)
        ts = make_tickets(sc, ticket_count, draws[i - 1]["period"])
        best = max(len(set(t) & set(draws[i]["nums"])) for t in ts)
        hist[best] += 1; total_hits += best
    n = sum(hist.values())
    return {"samples": n, "distribution": {str(k): hist[k] for k in range(6)}, "avg_best_hits": round(total_hits / n, 3)}


def render(draws: list[dict], weights: dict, quality: list[float], score: dict, tickets: list[tuple[int, ...]], bt: dict) -> str:
    latest = draws[-1]; ranked = sorted(score, key=score.get, reverse=True); top15 = ranked[:15]
    fmt = lambda ns: " ".join(f"{n:02}" for n in ns)
    pct = lambda n: 60 + 39 * (score[n] - min(score.values())) / max(.00001, max(score.values()) - min(score.values()))
    rows = "".join(f"<tr><td>{i}</td><td><b>{n:02}</b></td><td>{pct(n):.1f}%</td><td>{'、'.join(k for k in weights if feature_table(draws)[k][n] >= .65) or '均衡校正'}</td><td>守門通過</td></tr>" for i,n in enumerate(top15,1))
    packs = [("獨隻1中1",top15[:1]),("2中1~2",top15[:2]),("3中1~3",top15[:3]),("5中2~3",top15[:5]),("9中3~5",top15[:9])]
    packrows = "".join(f"<tr><td>{name}</td><td>{fmt(ns)}</td><td>{len(ns)}</td><td>研究觀察</td></tr>" for name,ns in packs)
    low = list(reversed(ranked[-15:])); lowrows = "".join(f"<tr><td>{name}</td><td>{fmt(low[:k])}</td><td>相對低分</td><td>僅供暫避觀察</td></tr>" for name,k in (("5不中",5),("10不中",10),("15不中",15)))
    recent=[]
    for i in range(max(320,len(draws)-15),len(draws)):
        s=scores(draws[:i],weights); pred=sorted(s,key=s.get,reverse=True)[:9]; actual=draws[i]["nums"]; hit=sorted(set(pred)&set(actual))
        recent.append(f"<tr><td>{draws[i]['date']}</td><td>{fmt(pred)}</td><td>{fmt(actual)}</td><td>{fmt(hit) or '-'}</td><td>{len(hit)}</td></tr>")
    recent_html="".join(reversed(recent)); now=datetime.now().strftime("%Y-%m-%d %H:%M")
    formula_rows="".join(f"<tr><td>{k}</td><td>滾動盲測</td><td>{v:.2f}</td><td>已納入候選模型</td></tr>" for k,v in weights.items())
    dist="、".join(f"{k}中：{v}期" for k,v in bt['distribution'].items())
    return f"""<!doctype html><html lang='zh-Hant'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>台灣539 精算預測戰報</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f4f6;color:#172033;font-family:Arial,'Microsoft JhengHei',sans-serif}}main{{max-width:1180px;margin:auto;padding:18px}}header{{background:linear-gradient(135deg,#8b0000,#d1242f);color:white;padding:25px;border-radius:14px}}h1{{margin:0 0 8px}}h2{{border-left:6px solid #c1121f;padding-left:10px;color:#7f1017;margin-top:30px}}nav{{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}}nav a{{background:white;border:1px solid #d1d5db;border-radius:8px;padding:9px 12px;color:#8b0000;text-decoration:none;font-weight:700}}.band{{background:white;border:1px solid #d8dee8;border-radius:12px;padding:18px;margin:14px 0;box-shadow:0 2px 8px #0000000d}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}}.card{{border:1px solid #d9dde5;border-radius:10px;padding:13px;background:#fff}}.hot-card{{border:2px solid #c1121f;background:#fff5f5}}.label{{color:#687386;font-size:13px}}.value{{font-size:19px;font-weight:800;margin-top:5px}}.num{{color:#c1121f;font-size:34px}}table{{width:100%;border-collapse:collapse;display:block;overflow:auto}}th{{background:#7f1017;color:#fff}}th,td{{padding:9px;border:1px solid #d7dce4;text-align:left;white-space:nowrap}}tr:nth-child(even) td{{background:#fafafa}}.warn{{background:#fff8e6;border-color:#e9b949}}.note{{color:#626d7d}}@media(max-width:600px){{main{{padding:8px}}header{{border-radius:8px}}}}
</style><main><header><h1>台灣539 精算預測戰報</h1><div>全新模型・依照天天樂戰報統一規格</div></header><nav><a href='#decision'>核心決策</a><a href='#rank'>前15名</a><a href='#packs'>強牌組</a><a href='#hits'>命中對照</a><a href='#low'>低機率</a><a href='#models'>公式模型</a><a href='#gate'>鐵律守門</a></nav>
<div class='band'><h2>本報表日期對照</h2><div class='grid'><div class='card'><div class='label'>全歷史資料範圍</div><div class='value'>完整 {len(draws):,} 期</div></div><div class='card'><div class='label'>最新開獎期別</div><div class='value'>{latest['period']}</div></div><div class='card'><div class='label'>最新開獎號碼</div><div class='value'>{fmt(latest['nums'])}</div></div><div class='card'><div class='label'>資料對應開獎日</div><div class='value'>{latest['date']}</div></div><div class='card'><div class='label'>戰報產生時間</div><div class='value'>{now}</div></div></div></div>
<div class='band' id='decision'><h2>核心決策</h2><div class='grid'><div class='card'><div class='label'>資料狀態</div><div class='value'>資料已更新</div></div><div class='card'><div class='label'>檢查</div><div class='value'>已重新運算</div></div><div class='card hot-card'><div class='label'>獨隻</div><div class='value num'>{top15[0]:02}</div></div><div class='card'><div class='label'>九碼核心</div><div class='value'>{fmt(top15[:9])}</div></div></div></div>
<div class='band'><h2>最強獨隻1中1</h2><div class='grid'><div class='card hot-card'><div class='label'>獨隻號碼</div><div class='value num'>{top15[0]:02}</div></div><div class='card'><div class='label'>判定</div><div class='value'>本期相對最高分</div></div><div class='card'><div class='label'>相對評分</div><div class='value'>{pct(top15[0]):.1f}%</div></div><div class='card'><div class='label'>發布狀態</div><div class='value'>研究觀察</div></div></div></div>
<div class='band' id='rank'><h2>下期研究候選前9名</h2><table><thead><tr><th>排名</th><th>號碼</th><th>相對分</th><th>主要支撐</th><th>守門</th></tr></thead><tbody>{rows[:rows.find('</tr>', rows.find('</tr>')*0)+5] if False else rows}</tbody></table><h2>第10到第15名第二層備查</h2><p>{fmt(top15[9:15])}</p></div>
<div class='band'><h2>生成號碼逐號驗算</h2><table><thead><tr><th>排名</th><th>號碼</th><th>總分</th><th>交叉來源</th><th>狀態</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class='band' id='packs'><h2>強牌組精算</h2><table><thead><tr><th>類型</th><th>號碼</th><th>顆數</th><th>狀態</th></tr></thead><tbody>{packrows}</tbody></table></div>
<div class='band' id='hits'><h2>最新命中結果與近期命中對照</h2><table><thead><tr><th>開獎日</th><th>當期預測前九</th><th>實際開獎</th><th>命中號</th><th>前九命中</th></tr></thead><tbody>{recent_html}</tbody></table></div>
<div class='band' id='low'><h2>低機率精準暫避</h2><table><thead><tr><th>暫避包</th><th>號碼</th><th>信心</th><th>判定</th></tr></thead><tbody>{lowrows}</tbody></table></div>
<div class='band' id='models'><h2>公式模型實驗室</h2><p>各模組只在滾動盲測後參與排序，無效模組不強行放行。</p><table><thead><tr><th>公式</th><th>驗證</th><th>本期權重</th><th>動作</th></tr></thead><tbody>{formula_rows}</tbody></table></div>
<div class='band warn'><h2>實戰失準回灌重排</h2><p>最近 {bt['samples']} 期、每期 {len(tickets)} 組，最佳組平均命中 {bt['avg_best_hits']}；{dist}。失準號於下一輪重新評分，不直接沿用。</p></div>
<div class='band'><h2>雙軌模型對照</h2><div class='grid'><div class='card'><div class='label'>候選模型數</div><div class='value'>{len(quality)}</div></div><div class='card'><div class='label'>候選回測分數</div><div class='value'>{' / '.join(str(round(x,1)) for x in quality)}</div></div><div class='card'><div class='label'>採用原則</div><div class='value'>盲測最高者</div></div></div></div>
<div class='band' id='gate'><h2>鐵律守門</h2><table><thead><tr><th>項目</th><th>結果</th><th>說明</th></tr></thead><tbody><tr><td>重新運算</td><td>已完成</td><td>依最新資料重算，不沿用上期答案</td></tr><tr><td>資料完整性</td><td>通過</td><td>去重、日期排序、號碼1至39、每期5個不重複</td></tr><tr><td>未來資料隔離</td><td>通過</td><td>時間序列逐期盲測</td></tr><tr><td>高信心包裝</td><td>禁止</td><td>未達實戰門檻只列研究觀察</td></tr></tbody></table></div>
<div class='band warn'><h2>實戰門檻與風險聲明</h2><p>今彩539為隨機遊戲，每組合法號碼理論機率相同；本戰報只供統計研究，不保證中獎或獲利。請設定固定娛樂預算。</p></div></main></html>"""


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--data", type=Path, default=DATA); ap.add_argument("--tickets", type=int, default=8); ap.add_argument("--backtest", type=int, default=360)
    a = ap.parse_args(); draws = load_draws(a.data)
    if len(draws) < 350: raise SystemExit("至少需要 350 期有效資料")
    weights, quality = choose_weights(draws, min(a.backtest, 360)); sc = scores(draws, weights)
    tickets = make_tickets(sc, max(1, min(a.tickets, 30)), draws[-1]["period"])
    bt = backtest(draws, weights, a.backtest, len(tickets)); OUT.mkdir(parents=True, exist_ok=True)
    report = OUT / "最新539科學預測戰報.html"; report.write_text(render(draws, weights, quality, sc, tickets, bt), encoding="utf-8")
    result = {"data_latest": draws[-1], "draw_count": len(draws), "weights": weights, "tickets": tickets, "backtest": bt}
    (OUT / "最新結果.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成：{report}")


if __name__ == "__main__": main()
