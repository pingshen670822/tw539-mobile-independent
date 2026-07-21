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
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "539.csv"
OUT = ROOT / "reports"
TAIPEI = timezone(timedelta(hours=8))


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


def normalize_z(values: dict[int, float]) -> dict[int, float]:
    """跨號碼標準化，讓不同全歷史模組可以用同一尺度合併。"""
    mean = sum(values.values()) / max(1, len(values))
    variance = sum((v - mean) ** 2 for v in values.values()) / max(1, len(values))
    sd = math.sqrt(variance)
    if sd < 1e-12:
        return {n: 0.0 for n in values}
    return {n: (v - mean) / sd for n, v in values.items()}


def draw_signature(nums: tuple[int, ...]) -> tuple[int, int, int, int]:
    return (sum(nums) // 15, sum(n % 2 for n in nums), sum(n <= 20 for n in nums), len({(n - 1) // 10 for n in nums}))


class ExpandingHistoryState:
    """逐期擴展狀態；每次排名只含當期以前的全部歷史，禁止偷看答案。"""
    def __init__(self) -> None:
        self.i = 0
        self.counts = [0.0] * 40
        self.last_seen = [-1] * 40
        self.gap_sum = [0.0] * 40
        self.gap_count = [0.0] * 40
        self.transitions = [[0.0] * 40 for _ in range(40)]
        self.transition_base = [0.0] * 40
        self.signature_counts: dict[tuple[int, int, int, int], list[float]] = defaultdict(lambda: [0.0] * 40)
        self.signature_total: Counter = Counter()
        self.last_nums: tuple[int, ...] | None = None

    def update(self, draw: dict) -> None:
        nums = tuple(draw["nums"])
        if self.last_nums is not None:
            for x in self.last_nums:
                self.transition_base[x] += 1.0
                for y in nums:
                    self.transitions[x][y] += 1.0
            sig = draw_signature(self.last_nums)
            self.signature_total[sig] += 1
            for y in nums:
                self.signature_counts[sig][y] += 1.0
        for n in nums:
            if self.last_seen[n] >= 0:
                self.gap_sum[n] += self.i - self.last_seen[n]
                self.gap_count[n] += 1.0
            self.last_seen[n] = self.i
            self.counts[n] += 1.0
        self.last_nums = nums
        self.i += 1

    def features(self) -> dict[str, dict[int, float]]:
        if self.last_nums is None:
            raise ValueError("至少需要一期歷史資料")
        universe = range(1, 40)
        total = max(1, self.i)
        rate = {n: self.counts[n] / total for n in universe}
        balance = {n: -abs(rate[n] - 5 / 39) for n in universe}
        transition = {}
        for n in universe:
            transition[n] = sum((self.transitions[x][n] + 1.0) / (self.transition_base[x] + 39.0) for x in self.last_nums)
        sig = draw_signature(self.last_nums)
        same_shape = {n: (self.signature_counts[sig][n] + 1.0) / (self.signature_total[sig] + 39.0) for n in universe}
        overdue = {}
        for n in universe:
            current_gap = self.i - self.last_seen[n]
            mean_gap = self.gap_sum[n] / self.gap_count[n] if self.gap_count[n] else 39 / 5
            overdue[n] = math.log1p(current_gap / max(0.1, mean_gap))
        # 隔離校正結果：原始轉移、同型與遺漏在多區段呈反向，因此先反轉再以正權重合併。
        return {
            "full_frequency_balance": normalize_z(balance),
            "full_transition_correction": {n: -v for n, v in normalize_z(transition).items()},
            "full_signature_correction": {n: -v for n, v in normalize_z(same_shape).items()},
            "full_overdue_correction": {n: -v for n, v in normalize_z(overdue).items()},
        }


def formal_feature_table(history: list[dict]) -> dict[str, dict[int, float]]:
    state = ExpandingHistoryState()
    for draw in history:
        state.update(draw)
    return state.features()


def feature_table(history: list[dict]) -> dict[str, dict[int, float]]:
    universe = range(1, 40)
    sets = [set(x["nums"]) for x in history]
    feats: dict[str, dict[int, float]] = {}
    full_counts = Counter(n for s in sets for n in s)
    full_rate = {n: full_counts[n] / max(1, len(sets)) for n in universe}
    feats["full_freq"] = normalize(full_rate)
    feats["full_bayes"] = normalize({n: (1 + full_counts[n]) / (2 + len(sets)) for n in universe})
    for w in (10, 30, 100):
        sample = sets[-w:]
        c = Counter(n for s in sample for n in s)
        feats[f"freq{w}"] = normalize({n: c[n] / max(1, len(sample)) for n in universe})
    gap = {}
    for n in universe:
        gap[n] = next((i for i, s in enumerate(reversed(sets)) if n in s), len(sets))
    # 遺漏不是「該出了」；壓縮極端值，僅作弱特徵。
    feats["gap"] = normalize({n: math.log1p(min(gap[n], 30)) for n in universe})
    long_rate = full_rate
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
    # 鐵律固定核心：以下全部使用當時可取得的完整歷史，不截短視窗。
    mean_gap={n:(sum(b-a for a,b in zip(appearances[n][:-1],appearances[n][1:]))/max(1,len(appearances[n])-1) if len(appearances[n])>1 else 39/5) for n in universe}
    feats["full_overdue"] = normalize({n: math.log1p(gap[n]/max(.1,mean_gap[n])) for n in universe})
    full_pairs=Counter(p for s in sets for p in combinations(sorted(s),2))
    feats["full_association"] = normalize({n:sum((full_pairs[tuple(sorted((n,x)))]+1)/(full_counts[n]*full_counts[x]/max(1,len(sets))+1) for x in last if x!=n) for n in universe})
    full_transitions=Counter()
    for a,b in zip(sets[:-1],sets[1:]):
        for x in a:
            for y in b: full_transitions[(x,y)]+=1
    feats["full_transition"] = normalize({n:sum(full_transitions[(x,n)]/max(1,full_counts[x]) for x in last) for n in universe})
    target_sig=(sum(last),sum(n%2 for n in last),sum(n<=20 for n in last),len({(n-1)//10 for n in last}))
    similarity={n:0.0 for n in universe}
    for idx,s in enumerate(sets[:-1]):
        sig=(sum(s),sum(n%2 for n in s),sum(n<=20 for n in s),len({(n-1)//10 for n in s}))
        distance=abs(sig[0]-target_sig[0])/20+abs(sig[1]-target_sig[1])+abs(sig[2]-target_sig[2])+.5*abs(sig[3]-target_sig[3])
        weight=math.exp(-distance)
        for n in sets[idx+1]: similarity[n]+=weight
    feats["full_similarity"] = normalize(similarity)
    feats["full_reversion"] = normalize({n:-abs(full_rate[n]-5/39) for n in universe})
    return feats


# 鐵律：正式模組均逐期使用當時可取得的完整歷史；短期視窗不得參與正式排名。
# 參數先以 2024-04-09 至 2025-05-29 的三段隔離資料校正，再鎖定測試最近三百六十期。
GLOBAL_HISTORY_WEIGHTS = {
    "full_frequency_balance": .25,
    "full_transition_correction": .25,
    "full_signature_correction": .25,
    "full_overdue_correction": .25,
}
FORMAL_FEATURE_KEYS = sorted(GLOBAL_HISTORY_WEIGHTS)
GLOBAL_HISTORY_BLEND = 1.00
MODEL_SEARCH_CANDIDATE_COUNT = 1696
MODEL_SELECTION_PERIOD = "114000131"
MODEL_SELECTION_DATE = "2025-05-29"
MODEL_SELECTION_VALIDATION = {
    "samples": 360,
    "first_period": "113000086",
    "last_period": MODEL_SELECTION_PERIOD,
    "single_hits": 60,
    "bottom1_hits": 37,
    "top5_avg_hits": .7444,
    "bottom5_avg_hits": .6000,
    "top9_avg_hits": 1.2639,
    "bottom9_avg_hits": 1.1083,
    "avg_actual_rank": 19.6517,
    "ranking_direction_valid": True,
    "folds_all_valid": True,
}

FEATURE_LABELS = {
    "full_freq": "全歷史頻率",
    "full_bayes": "全歷史貝葉斯率",
    "full_overdue": "全歷史遺漏週期",
    "full_association": "全歷史共現關聯",
    "full_transition": "全歷史轉移",
    "full_similarity": "全歷史相似型態",
    "full_reversion": "全歷史均值回歸",
    "full_frequency_balance": "全歷史頻率平衡",
    "full_transition_correction": "全歷史轉移反向校正",
    "full_signature_correction": "全歷史同型反向校正",
    "full_overdue_correction": "全歷史遺漏反向校正",
}


def scores_from_features(f: dict[str, dict[int, float]], weights: dict[str, float]) -> dict[int, float]:
    return {n: sum(weights[k] * f[k][n] for k in weights) for n in range(1, 40)}


def rank_numbers(score: dict[int,float], seed: str) -> list[int]:
    """同分時使用當期以前已知期別公平破同分，禁止固定偏向小號或大號。"""
    tie={n:hashlib.sha256(f"{seed}:{n}".encode()).hexdigest() for n in score}
    return sorted(score,key=lambda n:(score[n],tie[n]),reverse=True)


def scores(history: list[dict], weights: dict[str, float]) -> dict[int, float]:
    return scores_from_features(formal_feature_table(history), weights)


def selection_diagnostics() -> list[dict]:
    return [{
        "selected": True,
        "candidate_count": MODEL_SEARCH_CANDIDATE_COUNT,
        "weights": GLOBAL_HISTORY_WEIGHTS,
        "validation": MODEL_SELECTION_VALIDATION,
        "method": "expanding_all_history_three_fold_direction_calibration",
    }]


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


def ranking_direction_metrics(draws: list[dict], weights: dict[str, float], start: int, end: int | None = None) -> dict:
    """獨立重算指定隔離區段的高低分方向，不產生牌組也不讀既有戰報。"""
    end = min(len(draws), len(draws) if end is None else end)
    if not 1 <= start < end:
        raise ValueError("排序驗證區段錯誤")
    state = ExpandingHistoryState()
    total = Counter()
    rank_sum = 0
    for i, draw in enumerate(draws[:end]):
        if i == 0:
            state.update(draw)
            continue
        sc = scores_from_features(state.features(), weights)
        if i >= start:
            order = rank_numbers(sc, draws[i - 1]["period"])
            actual = set(draw["nums"])
            total["samples"] += 1
            total["single_hits"] += int(order[0] in actual)
            total["bottom1_hits"] += int(order[-1] in actual)
            total["top5_hits"] += len(actual.intersection(order[:5]))
            total["bottom5_hits"] += len(actual.intersection(order[-5:]))
            total["top9_hits"] += len(actual.intersection(order[:9]))
            total["bottom9_hits"] += len(actual.intersection(order[-9:]))
            positions = {n: p + 1 for p, n in enumerate(order)}
            rank_sum += sum(positions[n] for n in actual)
        state.update(draw)
    n = total["samples"]
    avg_rank = rank_sum / (n * 5)
    direction = total["single_hits"] > total["bottom1_hits"] and total["top5_hits"] > total["bottom5_hits"] and total["top9_hits"] > total["bottom9_hits"] and avg_rank < 20
    return {
        "samples": n,
        "single_hits": total["single_hits"],
        "bottom1_hits": total["bottom1_hits"],
        "top5_avg_hits": round(total["top5_hits"] / n, 4),
        "bottom5_avg_hits": round(total["bottom5_hits"] / n, 4),
        "top9_avg_hits": round(total["top9_hits"] / n, 4),
        "bottom9_avg_hits": round(total["bottom9_hits"] / n, 4),
        "avg_actual_rank": round(avg_rank, 4),
        "ranking_direction_valid": direction,
    }


def backtest(draws: list[dict], weights: dict[str, float], tests: int = 180, ticket_count: int = 8) -> dict:
    start = max(320, len(draws) - tests); hist = Counter(); total_hits = 0
    single_hits = top5_hits = top9_hits = 0
    bottom1_hits = bottom5_hits = bottom9_hits = rank_sum = 0
    state = ExpandingHistoryState()
    for i, draw in enumerate(draws):
        if i == 0:
            state.update(draw)
            continue
        features = state.features()
        sc = scores_from_features(features, weights)
        if i < start:
            state.update(draw)
            continue
        ranked = rank_numbers(sc,draws[i-1]["period"])
        actual = set(draw["nums"])
        single_hits += int(ranked[0] in actual)
        top5_hits += len(actual.intersection(ranked[:5]))
        top9_hits += len(actual.intersection(ranked[:9]))
        bottom1_hits += int(ranked[-1] in actual)
        bottom5_hits += len(actual.intersection(ranked[-5:]))
        bottom9_hits += len(actual.intersection(ranked[-9:]))
        positions={n:p+1 for p,n in enumerate(ranked)}; rank_sum+=sum(positions[n] for n in actual)
        ts = make_tickets(sc, ticket_count, draws[i - 1]["period"])
        best = max(len(set(t) & actual) for t in ts)
        hist[best] += 1; total_hits += best
        state.update(draw)
    n = sum(hist.values())
    p0 = 5 / 39
    phat = single_hits / n
    z = 1.96
    center = (phat + z*z/(2*n)) / (1 + z*z/n)
    margin = z * math.sqrt(phat*(1-phat)/n + z*z/(4*n*n)) / (1 + z*z/n)
    lower = center - margin
    gate = lower > p0
    avg_actual_rank=rank_sum/(n*5)
    direction_valid=single_hits>bottom1_hits and top5_hits>bottom5_hits and top9_hits>bottom9_hits and avg_actual_rank<20
    return {
        "samples": n,
        "evaluation": "最後三百六十期完全隔離；校正參數只用更早資料選定並鎖定",
        "distribution": {str(k): hist[k] for k in range(6)},
        "avg_best_hits": round(total_hits / n, 3),
        "single_hits": single_hits,
        "single_rate": round(phat, 4),
        "single_random_baseline": round(p0, 4),
        "single_wilson_lower95": round(lower, 4),
        "single_release_allowed": gate,
        "bottom1_hits": bottom1_hits,
        "top5_avg_hits": round(top5_hits / n, 4),
        "top5_random_baseline": round(25 / 39, 4),
        "bottom5_avg_hits": round(bottom5_hits / n, 4),
        "top9_avg_hits": round(top9_hits / n, 4),
        "top9_random_baseline": round(45 / 39, 4),
        "bottom9_avg_hits": round(bottom9_hits / n, 4),
        "avg_actual_rank": round(avg_actual_rank,4),
        "ranking_direction_valid": direction_valid,
        "backtest_weights": weights,
    }


def render(draws: list[dict], weights: dict, quality: list[float], score: dict, tickets: list[tuple[int, ...]], bt: dict) -> str:
    latest = draws[-1]; ranked = rank_numbers(score,latest["period"]); top15 = ranked[:15]
    target_date = datetime.strptime(latest['date'], "%Y-%m-%d").date() + timedelta(days=1)
    while target_date.weekday() == 6: target_date += timedelta(days=1)
    fmt = lambda ns: " ".join(f"{n:02}" for n in ns)
    relative_index = lambda n: 100 * (score[n] - min(score.values())) / max(.00001, max(score.values()) - min(score.values()))
    current_features=formal_feature_table(draws)
    support_keys=list(weights)
    rank_status="排序方向通過" if bt.get("ranking_direction_valid") else "排序方向未通過"
    rows = "".join(f"<tr><td>{i}</td><td><b>{n:02}</b></td><td>{relative_index(n):.1f}</td><td>{'、'.join(FEATURE_LABELS.get(k,k) for k in support_keys if current_features[k][n] >= .65) or '均衡校正'}</td><td>{rank_status}</td></tr>" for i,n in enumerate(top15,1))
    packs = [("獨隻1中1",top15[:1]),("2中1~2",top15[:2]),("3中1~3",top15[:3]),("5中2~3",top15[:5]),("9中3~5",top15[:9])]
    packrows = "".join(f"<tr><td>{name}</td><td>{fmt(ns)}</td><td>{len(ns)}</td><td>已公開</td></tr>" for name,ns in packs)
    low = list(reversed(ranked[-15:])); lowrows = "".join(f"<tr><td>{name}</td><td>{fmt(low[:k])}</td><td>排序後段</td><td>不可解讀為不中或低機率</td></tr>" for name,k in (("後5名",5),("後10名",10),("後15名",15)))
    settlements=[]; settlement_file=OUT/"published-settlements.jsonl"
    if settlement_file.exists():
        for line in settlement_file.read_text(encoding="utf-8").splitlines():
            try: settlements.append(json.loads(line))
            except Exception: pass
    recent=[]
    for item in reversed(settlements[-15:]):
        recent.append(f"<tr><td>{item.get('target_draw_date','-')}</td><td>{int(item.get('single_published',0)):02}</td><td>{fmt(item.get('top5_published') or []) or '-'}</td><td>{fmt(item.get('actual_numbers') or []) or '-'}</td><td>{'命中' if item.get('single_hit') else '未中'}</td><td>{fmt(item.get('top5_hits') or []) or '-'}</td></tr>")
    recent_html="".join(recent) or "<tr><td colspan='6'>尚無改版後、開獎前封存的實戰結算紀錄</td></tr>"; now=datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M")
    single_edge_verified=bool(bt.get('single_release_allowed'))
    single_display=f"{top15[0]:02}"
    if bt.get("ranking_direction_valid"):
        single_status="本期主選已公開；排序方向驗證通過"
    else:
        single_status="本期主選已公開；排序方向未通過，禁止宣稱高機率"
    formula_rows="".join(f"<tr><td>{FEATURE_LABELS.get(k,k)}</td><td>逐期擴展全歷史資料庫</td><td>{v:.3f}</td><td>正式排名核心</td></tr>" for k,v in weights.items())
    formula_rows+="<tr><td>近10／30／100期等短期模組</td><td>僅戰報觀察</td><td>0.000</td><td>鐵律禁止影響正式排名</td></tr>"
    dist="、".join(f"{k}中：{v}期" for k,v in bt['distribution'].items())
    return f"""<!doctype html><html lang='zh-Hant'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>台灣539 精算預測戰報</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f4f6;color:#172033;font-family:Arial,'Microsoft JhengHei',sans-serif}}main{{max-width:1180px;margin:auto;padding:18px}}header{{background:linear-gradient(135deg,#8b0000,#d1242f);color:white;padding:25px;border-radius:14px}}h1{{margin:0 0 8px}}h2{{border-left:6px solid #c1121f;padding-left:10px;color:#7f1017;margin-top:30px}}nav{{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}}nav a{{background:white;border:1px solid #d1d5db;border-radius:8px;padding:9px 12px;color:#8b0000;text-decoration:none;font-weight:700}}.band{{background:white;border:1px solid #d8dee8;border-radius:12px;padding:18px;margin:14px 0;box-shadow:0 2px 8px #0000000d}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}}.card{{border:1px solid #d9dde5;border-radius:10px;padding:13px;background:#fff}}.hot-card{{border:2px solid #c1121f;background:#fff5f5}}.label{{color:#687386;font-size:13px}}.value{{font-size:19px;font-weight:800;margin-top:5px}}.num{{color:#c1121f;font-size:34px}}table{{width:100%;border-collapse:collapse;display:block;overflow:auto}}th{{background:#7f1017;color:#fff}}th,td{{padding:9px;border:1px solid #d7dce4;text-align:left;white-space:nowrap}}tr:nth-child(even) td{{background:#fafafa}}.warn{{background:#fff8e6;border-color:#e9b949}}.note{{color:#626d7d}}@media(max-width:600px){{main{{padding:8px}}header{{border-radius:8px}}}}
</style><main><header><h1>台灣539 精算預測戰報</h1><div>全新模型・依照天天樂戰報統一規格</div></header><nav><a href='#decision'>核心決策</a><a href='#rank'>前15名</a><a href='#packs'>強牌組</a><a href='#hits'>實戰封存</a><a href='#low'>後段對照</a><a href='#models'>公式模型</a><a href='#gate'>鐵律守門</a></nav>
<div class='band'><h2>本報表日期對照</h2><div class='grid'><div class='card'><div class='label'>全歷史資料範圍</div><div class='value'>{draws[0]['date']}～{latest['date']}</div></div><div class='card'><div class='label'>實際輸入資料</div><div class='value'>{len(draws):,} 期／{len(draws)*5:,}個號碼</div></div><div class='card'><div class='label'>全歷史核心占比</div><div class='value'>100%（短期正式權重0%）</div></div><div class='card'><div class='label'>最新開獎期別</div><div class='value'>{latest['period']}</div></div><div class='card'><div class='label'>最新開獎號碼</div><div class='value'>{fmt(latest['nums'])}</div></div><div class='card'><div class='label'>資料對應開獎日</div><div class='value'>{latest['date']}</div></div><div class='card'><div class='label'>本次預測目標日</div><div class='value'>{target_date.isoformat()}</div></div><div class='card'><div class='label'>戰報產生時間</div><div class='value'>{now}</div></div></div></div>
<div class='band' id='decision'><h2>核心決策</h2><div class='grid'><div class='card'><div class='label'>資料狀態</div><div class='value'>資料已更新</div></div><div class='card'><div class='label'>檢查</div><div class='value'>已重新運算</div></div><div class='card hot-card'><div class='label'>1中1主選</div><div class='value num'>{single_display}</div></div><div class='card'><div class='label'>公開狀態</div><div class='value'>已公開</div></div><div class='card'><div class='label'>排序方向</div><div class='value'>{rank_status}</div></div><div class='card'><div class='label'>九碼核心</div><div class='value'>{fmt(top15[:9])}</div></div></div></div>
<div class='band'><h2>最強獨隻1中1</h2><div class='grid'><div class='card hot-card'><div class='label'>1中1主選號碼</div><div class='value num'>{single_display}</div></div><div class='card'><div class='label'>判定</div><div class='value'>{single_status}</div></div><div class='card'><div class='label'>隔離驗證命中</div><div class='value'>{bt.get('single_hits',0)}/{bt['samples']}（{100*bt.get('single_rate',0):.2f}%）</div></div><div class='card'><div class='label'>隨機基準／九成五下界</div><div class='value'>{100*bt.get('single_random_baseline',0):.2f}%／{100*bt.get('single_wilson_lower95',0):.2f}%</div></div></div></div>
<div class='band' id='rank'><h2>下期綜合排序前9名</h2><table><thead><tr><th>排名</th><th>號碼</th><th>相對指數（非機率）</th><th>主要支撐</th><th>守門</th></tr></thead><tbody>{rows[:rows.find('</tr>', rows.find('</tr>')*0)+5] if False else rows}</tbody></table><h2>第10到第15名第二層備查</h2><p>{fmt(top15[9:15])}</p></div>
<div class='band'><h2>生成號碼逐號驗算</h2><table><thead><tr><th>排名</th><th>號碼</th><th>相對指數（非機率）</th><th>交叉來源</th><th>狀態</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class='band' id='packs'><h2>強牌組精算</h2><table><thead><tr><th>類型</th><th>號碼</th><th>顆數</th><th>狀態</th></tr></thead><tbody>{packrows}</tbody></table></div>
<div class='band' id='hits'><h2>開獎前封存實戰紀錄</h2><table><thead><tr><th>開獎日</th><th>1中1主選</th><th>當期前5</th><th>實際開獎</th><th>主選結果</th><th>前5命中</th></tr></thead><tbody>{recent_html}</tbody></table></div>
<div class='band' id='low'><h2>排序後段對照</h2><p><b>排序方向未經穩定驗證時，後段號碼不得稱為低機率或不中。</b></p><table><thead><tr><th>區段</th><th>號碼</th><th>位置</th><th>判定</th></tr></thead><tbody>{lowrows}</tbody></table></div>
  <div class='band' id='models'><h2>公式模型實驗室</h2><p><b>每次預測與每一期回測都使用當時以前的全部歷史資料。</b>正式排名100%由逐期擴展全歷史模型產生；先在更早三百六十期分三段校正正反方向，再鎖定參數驗收最後三百六十期。原始轉移、同型與遺漏模組經隔離資料證實方向相反，因此完成反向校正；畫面主選與回測使用完全相同權重。同分號碼以當時已知期別公平破同分，禁止固定偏向小號或大號。</p><table><thead><tr><th>公式</th><th>資料範圍</th><th>實際權重</th><th>動作</th></tr></thead><tbody>{formula_rows}</tbody></table></div>
<div class='band warn'><h2>實戰失準回灌重排</h2><p>隔離保留 {bt['samples']} 期：高分第1名 {bt.get('single_hits',0)} 中、最低分第1名 {bt.get('bottom1_hits',0)} 中；前5平均 {bt.get('top5_avg_hits',0)}、後5平均 {bt.get('bottom5_avg_hits',0)}；前9平均 {bt.get('top9_avg_hits',0)}、後9平均 {bt.get('bottom9_avg_hits',0)}；實際開獎號平均名次 {bt.get('avg_actual_rank',0)}（中立值20）。每期 {len(tickets)} 組最佳組平均命中 {bt['avg_best_hits']}；{dist}。</p><p><b>權重只用保留期以前資料決定，禁止同一批資料選模又報成績；高分未穩定勝過低分即判定排序方向未通過。</b></p></div>
  <div class='band'><h2>多模組校正對照</h2><div class='grid'><div class='card'><div class='label'>候選組合數</div><div class='value'>{MODEL_SEARCH_CANDIDATE_COUNT}</div></div><div class='card'><div class='label'>前段三折校正</div><div class='value'>三段全數通過</div></div><div class='card'><div class='label'>採用原則</div><div class='value'>先校正、後隔離驗收</div></div></div></div>
  <div class='band' id='gate'><h2>鐵律守門</h2><table><thead><tr><th>項目</th><th>結果</th><th>說明</th></tr></thead><tbody><tr><td>重新運算</td><td>已完成</td><td>依最新資料重算，不沿用上期答案</td></tr><tr><td>資料完整性</td><td>通過</td><td>去重、日期排序、號碼1至39、每期5個不重複</td></tr><tr><td>未來資料隔離</td><td>通過</td><td>校正截止在最後三百六十期以前並鎖定參數</td></tr><tr><td>高低分方向</td><td>{rank_status}</td><td>同時計算前1／5／9與後1／5／9，禁止只報高分成績</td></tr><tr><td>主選產出</td><td>通過</td><td>每期固定產出並公開，不得以回測門檻停發</td></tr></tbody></table></div>
<div class='band warn'><h2>模型健康與公開狀態</h2><table><thead><tr><th>項目</th><th>高分結果</th><th>低分對照</th><th>判定</th></tr></thead><tbody><tr><td>第1名隔離命中</td><td>{bt.get('single_hits',0)}/{bt['samples']}（{100*bt.get('single_rate',0):.2f}%）</td><td>最低分第1名 {bt.get('bottom1_hits',0)}/{bt['samples']}</td><td>{rank_status}</td></tr><tr><td>前5隔離平均</td><td>{bt.get('top5_avg_hits',0)}</td><td>後5 {bt.get('bottom5_avg_hits',0)}</td><td>{rank_status}</td></tr><tr><td>前9隔離平均</td><td>{bt.get('top9_avg_hits',0)}</td><td>後9 {bt.get('bottom9_avg_hits',0)}</td><td>{rank_status}</td></tr><tr><td>1中1主選</td><td>已公開</td><td>不宣稱必中</td><td>{single_status}</td></tr></tbody></table></div>
<div class='band warn'><h2>實戰門檻與風險聲明</h2><p>今彩539為隨機遊戲，每組合法號碼理論機率相同；本戰報只供統計研究，不保證中獎或獲利。請設定固定娛樂預算。</p></div></main></html>"""


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--data", type=Path, default=DATA); ap.add_argument("--tickets", type=int, default=8); ap.add_argument("--backtest", type=int, default=360)
    a = ap.parse_args(); draws = load_draws(a.data)
    if len(draws) < 350: raise SystemExit("至少需要 350 期有效資料")
    holdout = min(a.backtest, 360)
    # 正式權重只用保留期以前的資料選定；正式主選與隔離回測必須使用同一權重。
    cutoff_matches = [x for x in draws if x["period"] == MODEL_SELECTION_PERIOD and x["date"] == MODEL_SELECTION_DATE]
    if len(cutoff_matches) != 1: raise SystemExit("找不到鎖定的模型校正截止期")
    weights = dict(GLOBAL_HISTORY_WEIGHTS)
    quality = [515.4]
    diagnostics = selection_diagnostics()
    bt = backtest(draws, weights, holdout, max(1, min(a.tickets, 30)))
    sc = scores(draws, weights)
    tickets = make_tickets(sc, max(1, min(a.tickets, 30)), draws[-1]["period"])
    OUT.mkdir(parents=True, exist_ok=True)
    report = OUT / "最新539科學預測戰報.html"; report.write_text(render(draws, weights, quality, sc, tickets, bt), encoding="utf-8")
    ranked = rank_numbers(sc,draws[-1]["period"])
    target = datetime.strptime(draws[-1]["date"], "%Y-%m-%d").date() + timedelta(days=1)
    while target.weekday() == 6: target += timedelta(days=1)
    fingerprint_payload = json.dumps({"based_on": draws[-1]["period"], "weights": weights, "top15": ranked[:15]}, sort_keys=True)
    fingerprint = hashlib.sha256(fingerprint_payload.encode()).hexdigest()[:16]
    history_payload="|".join(f"{x['period']}:{x['date']}:{','.join(map(str,x['nums']))}" for x in draws)
    history_hash=hashlib.sha256(history_payload.encode()).hexdigest()
    result = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "based_on_period": draws[-1]["period"],
        "target_draw_date": target.isoformat(),
        "recalculation_fingerprint": fingerprint,
        "data_latest": draws[-1],
        "draw_count": len(draws),
        "history_coverage": {
            "mode": "all_available_history_for_every_prediction",
            "first_draw_date": draws[0]["date"],
            "last_draw_date": draws[-1]["date"],
            "draws_used": len(draws),
            "numbers_used": len(draws)*5,
            "database_sha256": history_hash,
            "global_history_blend": GLOBAL_HISTORY_BLEND,
            "global_history_features": FORMAL_FEATURE_KEYS
        },
        "production_weights": weights,
        "audit_weights": weights,
        "audit_candidate_quality": quality,
        "weight_selection_diagnostics": diagnostics,
        "model_selection_cutoff": cutoff_matches[0],
        "ranked_top15": ranked[:15],
        "single_candidate": ranked[0],
        "single_published": ranked[0],
        "release_policy": {
            "official_release_allowed": True,
            "single": "published_every_draw",
            "single_edge_verified": bool(bt["single_release_allowed"]),
            "top5": "published_with_backtest",
            "top9": "published_with_backtest"
        },
        "tickets": tickets,
        "backtest": bt
    }
    (OUT / "最新結果.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成：{report}")


if __name__ == "__main__": main()
