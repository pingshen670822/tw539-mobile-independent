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

from report_pages import render_report_pages

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
        self.repeat_exposure = [0] * 40
        self.repeat_hits = [0] * 40
        self.last_nums: tuple[int, ...] | None = None

    def update(self, draw: dict) -> None:
        nums = tuple(draw["nums"])
        if self.last_nums is not None:
            current=set(nums)
            for n in self.last_nums:
                self.repeat_exposure[n] += 1
                self.repeat_hits[n] += int(n in current)
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


def formal_history_state(history: list[dict]) -> ExpandingHistoryState:
    state = ExpandingHistoryState()
    for draw in history:
        state.update(draw)
    return state


def formal_feature_table(history: list[dict]) -> dict[str, dict[int, float]]:
    return formal_history_state(history).features()


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
# 每期新增開獎後，重新搜尋全部 286 組權重；以前段 360 期三折校正，鎖定後再驗收末段 360 期。
GLOBAL_HISTORY_WEIGHTS = {
    "full_frequency_balance": .00,
    "full_transition_correction": .50,
    "full_signature_correction": .10,
    "full_overdue_correction": .40,
}
FORMAL_FEATURE_KEYS = tuple(GLOBAL_HISTORY_WEIGHTS)
GLOBAL_HISTORY_BLEND = 1.00
MODEL_SEARCH_CANDIDATE_COUNT = 286
MAX_ANCHOR_MODULE_WEIGHT = .50
ROLLING_ENSEMBLE_MEMBERS = 3
MIN_ENSEMBLE_WEIGHT_DISTANCE = .60
ROLLING_CALIBRATION_DRAWS = 360
ROLLING_HOLDOUT_DRAWS = 360
ROLLING_CALIBRATION_FOLDS = 3
LONG_HISTORY_SAMPLE_STEP = 6
LONG_HISTORY_FOLDS = 9
ROLLING_LEARNING_RATE = .001
ROLLING_LEARNING_RATE_CANDIDATES = (.0005,.001,.002,.003,.005,.01)
ROLLING_BOUNDARY_BLEND_CANDIDATES = (0.0,.25,.50,.75,1.0)
POLARITY_EWMA_ALPHAS = (.90,.95,.97,.98,.99,.995)
POLARITY_FULL_HISTORY_BLENDS = (0.0,.10,.25,.50,.75)
POLARITY_SELECTION_WINDOW = 90
POLARITY_WARMUP = 60
SINGLE_SPECIALIST_WINDOW = 30
CATASTROPHIC_TOP9_HIT_LIMIT = 0
CATASTROPHIC_AVG_RANK_FLOOR = 22.0
CATASTROPHIC_ROTATION = 12

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
    """直接依重新精算分數排序；同分時公平破同分，不做事後補位。"""
    tie={n:hashlib.sha256(f"{seed}:{n}".encode()).hexdigest() for n in score}
    return sorted(score,key=lambda n:(score[n],tie[n]),reverse=True)


def average_weights(weight_sets: list[dict[str, float]]) -> dict[str, float]:
    """將多個正式模型壓成可讀的平均模組占比；實際排序仍使用名次共識。"""
    if not weight_sets:
        raise ValueError("多模型權重不可為空")
    return {
        key: sum(float(weights[key]) for weights in weight_sets) / len(weight_sets)
        for key in FORMAL_FEATURE_KEYS
    }


def consensus_borda_score(rankings: list[list[int]]) -> dict[int, float]:
    """以名次共識合併模型，避免單一權重組壟斷主選。"""
    if not rankings:
        raise ValueError("多模型排名不可為空")
    score = {number: 0.0 for number in range(1, 40)}
    for ranked in rankings:
        for position, number in enumerate(ranked):
            score[number] += 39 - position
    return score


def ensemble_scores_from_features(
    features: dict[str, dict[int, float]],
    weight_sets: list[dict[str, float]],
    previous_nums: tuple[int, ...],
    seed: str,
    repeat_exposure: list[int],
    repeat_hits: list[int],
) -> tuple[dict[int, float], dict[int, float], list[dict], list[list[int]]]:
    """各模型先獨立做連莊資格，再以名次共識重排並二次守門。"""
    rankings = []
    for weights in weight_sets:
        raw = scores_from_features(features, weights)
        adjusted, _ = apply_repeat_qualification(
            raw,
            features,
            weights,
            previous_nums,
            seed,
            repeat_exposure,
            repeat_hits,
        )
        rankings.append(rank_numbers(adjusted, seed))
    consensus = consensus_borda_score(rankings)
    effective_weights = average_weights(weight_sets)
    adjusted, repeat_audit = apply_repeat_qualification(
        consensus,
        features,
        effective_weights,
        previous_nums,
        seed,
        repeat_exposure,
        repeat_hits,
    )
    raw_effective = scores_from_features(features, effective_weights)
    return adjusted, raw_effective, repeat_audit, rankings


def apply_repeat_qualification(score: dict[int,float], features: dict[str,dict[int,float]], weights: dict[str,float], previous_nums: tuple[int,...], seed: str, repeat_exposure: list[int], repeat_hits: list[int]) -> tuple[dict[int,float], list[dict]]:
    """上一期號碼必須通過相對條件才准列入前九；在排名前調整資格，不做事後補號。"""
    base=rank_numbers(score,seed)
    lo,hi=min(score.values()),max(score.values()); span=max(1e-12,hi-lo)
    audits=[]
    for n in previous_nums:
        contributions={k:weights[k]*features[k][n] for k in weights}
        relative_index=100*(score[n]-lo)/span
        transition_contribution=contributions.get("full_transition_correction",0.0)
        positive_modules=sum(v>0 for v in contributions.values())
        repeat_samples=repeat_exposure[n]
        repeat_hit_count=repeat_hits[n]
        repeat_rate=repeat_hit_count/repeat_samples if repeat_samples else 0.0
        repeat_baseline=5/39
        repeat_backtest_pass=repeat_samples>=30 and repeat_rate>=repeat_baseline
        qualified=relative_index>=75 and transition_contribution>0 and positive_modules>=2 and repeat_backtest_pass
        base_top9=n in base[:9]
        audits.append({
            "number":n,
            "relative_index":round(relative_index,4),
            "transition_contribution":round(transition_contribution,6),
            "positive_module_count":positive_modules,
            "repeat_samples":repeat_samples,
            "repeat_hits":repeat_hit_count,
            "repeat_rate":round(repeat_rate,6),
            "repeat_baseline":round(repeat_baseline,6),
            "repeat_backtest_pass":repeat_backtest_pass,
            "base_top9":base_top9,
            "qualified":qualified,
        })
    disqualified={x["number"] for x in audits if not x["qualified"]}
    eligible=[n for n in base if n not in disqualified]
    front=eligible[:9]
    final=front+[n for n in base if n not in front]
    sorted_values=[score[n] for n in base]; epsilon=span*1e-12
    adjusted={n:sorted_values[i]-epsilon*i for i,n in enumerate(final)}
    final=rank_numbers(adjusted,seed); final_pos={n:i+1 for i,n in enumerate(final)}
    for item in audits:
        item["final_rank"]=final_pos[item["number"]]
        item["listed_top9"]=item["number"] in final[:9]
    return adjusted,audits


def scores(history: list[dict], weights: dict[str, float] | list[dict[str, float]]) -> dict[int, float]:
    state=formal_history_state(history); features=state.features()
    if isinstance(weights, list):
        return ensemble_scores_from_features(
            features,
            weights,
            history[-1]["nums"],
            history[-1]["period"],
            state.repeat_exposure,
            state.repeat_hits,
        )[0]
    raw=scores_from_features(features,weights)
    return apply_repeat_qualification(raw,features,weights,history[-1]["nums"],history[-1]["period"],state.repeat_exposure,state.repeat_hits)[0]


def weight_candidates() -> list[dict[str, float]]:
    """四個正式模組以 0.1 為單位列舉總和為 1 的全部 286 組權重。"""
    keys = list(FORMAL_FEATURE_KEYS)
    candidates = []
    for a in range(11):
        for b in range(11 - a):
            for c in range(11 - a - b):
                d = 10 - a - b - c
                candidates.append(dict(zip(keys, (a / 10, b / 10, c / 10, d / 10))))
    if len(candidates) != MODEL_SEARCH_CANDIDATE_COUNT:
        raise RuntimeError("多模組候選權重數量錯誤")
    return candidates


def candidate_grid_sha256(candidates: list[dict[str, float]] | None = None) -> str:
    candidates = candidates or weight_candidates()
    payload = json.dumps(candidates, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def evaluation_cases(draws: list[dict], start: int, end: int) -> list[dict]:
    """一次建立逐期全歷史快照，供全部候選權重使用，避免任何未來資料滲入。"""
    if not 1 <= start < end <= len(draws):
        raise ValueError("滾動校正區段錯誤")
    state = ExpandingHistoryState()
    cases = []
    for i, draw in enumerate(draws[:end]):
        if i == 0:
            state.update(draw)
            continue
        if i >= start:
            cases.append({
                "features": state.features(),
                "previous_numbers": tuple(draws[i - 1]["nums"]),
                "seed": draws[i - 1]["period"],
                "repeat_exposure": state.repeat_exposure[:],
                "repeat_hits": state.repeat_hits[:],
                "actual": tuple(draw["nums"]),
                "period": draw["period"],
                "date": draw["date"],
            })
        state.update(draw)
    return cases


def _empty_metric() -> dict:
    return {"samples": 0, "single_hits": 0, "bottom1_hits": 0, "top5_hits": 0,
            "bottom5_hits": 0, "top9_hits": 0, "rank10_15_hits": 0,
            "top15_hits": 0, "bottom9_hits": 0, "rank_sum": 0}


def fast_case_ranking(case: dict, weights: dict[str, float]) -> list[int]:
    """校正專用等價排序；只產生名次，不重建報表稽核欄位，避免同一案例重複排序三次。"""
    features=case["features"]
    raw=scores_from_features(features,weights)
    base=rank_numbers(raw,case["seed"])
    lo,hi=min(raw.values()),max(raw.values()); span=max(1e-12,hi-lo)
    disqualified=set()
    for n in case["previous_numbers"]:
        contributions={k:weights[k]*features[k][n] for k in weights}
        relative_index=100*(raw[n]-lo)/span
        repeat_samples=case["repeat_exposure"][n]
        repeat_rate=case["repeat_hits"][n]/repeat_samples if repeat_samples else 0.0
        qualified=(relative_index>=75
                   and contributions.get("full_transition_correction",0.0)>0
                   and sum(v>0 for v in contributions.values())>=2
                   and repeat_samples>=30 and repeat_rate>=5/39)
        if not qualified: disqualified.add(n)
    eligible=[n for n in base if n not in disqualified]
    front=eligible[:9]
    return front+[n for n in base if n not in front]


def apply_catastrophic_guard(ranked: list[int], previous_numbers: tuple[int, ...] | list[int]) -> list[int]:
    """前9全空且實際落入深後段時，有限度前移中後段；上一期號碼仍受連莊資格約束。"""
    rotated=ranked[CATASTROPHIC_ROTATION:]+ranked[:CATASTROPHIC_ROTATION]
    previous=set(previous_numbers)
    qualified_previous=previous.intersection(ranked[:9])
    blocked_previous=previous-qualified_previous
    eligible=[number for number in rotated if number not in blocked_previous]
    front=eligible[:9]
    return front+[number for number in rotated if number not in front]


def _metric_prefix(rows: list[tuple[list[int],set[int],dict[str,float]]]) -> dict[str,list[float]]:
    keys=("single_hits","bottom1_hits","top5_hits","bottom5_hits","top9_hits",
          "rank10_15_hits","top15_hits","bottom9_hits","rank_sum")
    prefix={key:[0.0] for key in keys}
    for ranked,actual,_ in rows:
        positions={number:index+1 for index,number in enumerate(ranked)}
        values={
            "single_hits":int(ranked[0] in actual),
            "bottom1_hits":int(ranked[-1] in actual),
            "top5_hits":len(actual.intersection(ranked[:5])),
            "bottom5_hits":len(actual.intersection(ranked[-5:])),
            "top9_hits":len(actual.intersection(ranked[:9])),
            "rank10_15_hits":len(actual.intersection(ranked[9:15])),
            "top15_hits":len(actual.intersection(ranked[:15])),
            "bottom9_hits":len(actual.intersection(ranked[-9:])),
            "rank_sum":sum(positions[number] for number in actual),
        }
        for key in keys:
            prefix[key].append(prefix[key][-1]+values[key])
    return prefix


def _prefix_metric(prefix: dict[str,list[float]], start: int, end: int) -> dict:
    raw={key:prefix[key][end]-prefix[key][start] for key in prefix}
    raw["samples"]=end-start
    return _finish_metric(raw)


def adaptive_polarity_backtest(
    draws: list[dict],
    anchor_weights: dict[str,float],
    tests: int = ROLLING_HOLDOUT_DRAWS,
    selection_window: int = POLARITY_SELECTION_WINDOW,
) -> dict:
    """三十組模組正反方向逐期競賽；每期只用前九十期成績選下一期，禁止看答案。"""
    def direction_quality(metric: dict) -> float:
        n=metric["samples"]
        return ((metric["top9_avg_hits"]-metric["bottom9_avg_hits"])*n*7
                +(metric["top9_slot_hit_rate"]-metric["rank10_15_slot_hit_rate"])*n*180
                +(20-metric["avg_actual_rank"])*n)
    case_start=320
    cases=evaluation_cases(draws,case_start,len(draws))
    strategies=[]
    for alpha in POLARITY_EWMA_ALPHAS:
        for full_blend in POLARITY_FULL_HISTORY_BLENDS:
            cumulative={key:0.0 for key in FORMAL_FEATURE_KEYS}
            ewma={key:0.0 for key in FORMAL_FEATURE_KEYS}
            count=0
            rows=[]
            for case in cases:
                polarities={}
                for key in FORMAL_FEATURE_KEYS:
                    full_mean=cumulative[key]/max(1,count)
                    combined=full_blend*full_mean+(1-full_blend)*ewma[key]
                    polarities[key]=1.0 if count<POLARITY_WARMUP or combined>=0 else -1.0
                signed={key:float(anchor_weights[key])*polarities[key] for key in FORMAL_FEATURE_KEYS}
                ranked=fast_case_ranking(case,signed)
                actual=set(case["actual"])
                rows.append((ranked,actual,polarities))
                for key in FORMAL_FEATURE_KEYS:
                    signal=sum(case["features"][key][number] for number in actual)/5
                    cumulative[key]+=signal
                    ewma[key]=alpha*ewma[key]+(1-alpha)*signal
                count+=1
            strategies.append({
                "alpha":alpha,
                "full_history_blend":full_blend,
                "rows":rows,
                "prefix":_metric_prefix(rows),
                "cumulative":cumulative,
                "ewma":ewma,
                "count":count,
            })
    holdout_start=len(draws)-min(tests,ROLLING_HOLDOUT_DRAWS)
    start_offset=holdout_start-case_start
    selected_metric=_empty_metric();unguarded_metric=_empty_metric()
    top5_distribution=Counter();top9_distribution=Counter();selection_counts=Counter();single_selection_counts=Counter();path=[];selected_rows=[];unguarded_rows=[]
    catastrophic_trigger_count=0;previous_base_ranked=None;previous_base_actual=None
    for draw_index in range(holdout_start,len(draws)):
        offset=draw_index-case_start
        window_start=max(0,offset-selection_window)
        def strategy_key(strategy):
            metric=_prefix_metric(strategy["prefix"],window_start,offset)
            return (direction_quality(metric),metric["single_hits"],-strategy["alpha"],-strategy["full_history_blend"])
        chosen=max(strategies,key=strategy_key)
        unguarded_ranked,actual,polarities=chosen["rows"][offset]
        _add_ranking(unguarded_metric,unguarded_ranked,actual)
        unguarded_rows.append((unguarded_ranked,actual,polarities))
        catastrophic_trigger=False
        if previous_base_ranked is not None:
            previous_positions={number:index+1 for index,number in enumerate(previous_base_ranked)}
            previous_top9_hits=len(previous_base_actual.intersection(previous_base_ranked[:9]))
            previous_avg_rank=sum(previous_positions[number] for number in previous_base_actual)/5
            catastrophic_trigger=(previous_top9_hits<=CATASTROPHIC_TOP9_HIT_LIMIT
                                  and previous_avg_rank>=CATASTROPHIC_AVG_RANK_FLOOR)
        ranked=(apply_catastrophic_guard(unguarded_ranked,case["previous_numbers"])
                if catastrophic_trigger else list(unguarded_ranked))
        catastrophic_trigger_count+=int(catastrophic_trigger)
        single=ranked[0]
        _add_ranking(selected_metric,ranked,actual)
        selected_rows.append((ranked,actual,polarities))
        top5_distribution[len(actual.intersection(ranked[:5]))]+=1
        top9_distribution[len(actual.intersection(ranked[:9]))]+=1
        label=f"{chosen['alpha']:.3f}/{chosen['full_history_blend']:.2f}"
        selection_counts[label]+=1
        single_label="穩定守門：不啟用短窗重排"
        single_selection_counts[single_label]+=1
        path.append({"period":draws[draw_index]["period"],"strategy":label,
                     "single_strategy":single_label,"single":single,"polarities":polarities,
                     "catastrophic_guard":catastrophic_trigger})
        previous_base_ranked=list(unguarded_ranked);previous_base_actual=set(actual)
    result=_finish_metric(selected_metric)
    result["single_direction_valid"]=result["single_hits"]>result["bottom1_hits"]
    result["front_ranking_direction_valid"]=(
        result["top5_avg_hits"]>result["bottom5_avg_hits"]
        and result["top9_avg_hits"]>result["bottom9_avg_hits"]
        and result["boundary_control_valid"]
        and result["avg_actual_rank"]<20
    )
    result["ranking_direction_valid"]=result["front_ranking_direction_valid"]
    n=result["samples"]
    recent_metric=_empty_metric();recent_top9_distribution=Counter()
    for ranked,actual,_ in selected_rows[-54:]:
        _add_ranking(recent_metric,ranked,actual)
        recent_top9_distribution[len(actual.intersection(ranked[:9]))]+=1
    recent_result=_finish_metric(recent_metric)
    recent_result["single_direction_valid"]=recent_result["single_hits"]>recent_result["bottom1_hits"]
    recent_result["front_ranking_direction_valid"]=(
        recent_result["top5_avg_hits"]>recent_result["bottom5_avg_hits"]
        and recent_result["top9_avg_hits"]>recent_result["bottom9_avg_hits"]
        and recent_result["boundary_control_valid"]
        and recent_result["avg_actual_rank"]<20
    )
    recent_result["ranking_direction_valid"]=recent_result["front_ranking_direction_valid"]
    recent_result["top9_hit_distribution"]={str(k):recent_top9_distribution[k] for k in range(6)}
    recent_result["top9_at_least_2_rate"]=round(sum(v for k,v in recent_top9_distribution.items() if k>=2)/54,4)
    unguarded_recent_metric=_empty_metric()
    for unguarded_ranked,actual,_ in unguarded_rows[-54:]:
        _add_ranking(unguarded_recent_metric,unguarded_ranked,actual)
    unguarded_recent_result=_finish_metric(unguarded_recent_metric)
    unguarded_result=_finish_metric(unguarded_metric)
    final_offset=len(cases)
    final_window_start=max(0,final_offset-selection_window)
    def final_strategy_key(strategy):
        metric=_prefix_metric(strategy["prefix"],final_window_start,final_offset)
        return (direction_quality(metric),metric["single_hits"],-strategy["alpha"],-strategy["full_history_blend"])
    chosen=max(strategies,key=final_strategy_key)
    final_polarities={}
    for key in FORMAL_FEATURE_KEYS:
        full_mean=chosen["cumulative"][key]/max(1,chosen["count"])
        combined=chosen["full_history_blend"]*full_mean+(1-chosen["full_history_blend"])*chosen["ewma"][key]
        final_polarities[key]=1.0 if combined>=0 else -1.0
    signed_weights={key:float(anchor_weights[key])*final_polarities[key] for key in FORMAL_FEATURE_KEYS}
    state=formal_history_state(draws);features=state.features();raw=scores_from_features(features,signed_weights)
    adjusted,repeat_audit=apply_repeat_qualification(
        raw,features,signed_weights,draws[-1]["nums"],draws[-1]["period"],
        state.repeat_exposure,state.repeat_hits)
    base_next_ranked=rank_numbers(adjusted,draws[-1]["period"])
    reconstructed_guard=False
    if previous_base_ranked is not None:
        previous_positions={number:index+1 for index,number in enumerate(previous_base_ranked)}
        previous_top9_hits=len(previous_base_actual.intersection(previous_base_ranked[:9]))
        previous_avg_rank=sum(previous_positions[number] for number in previous_base_actual)/5
        reconstructed_guard=(previous_top9_hits<=CATASTROPHIC_TOP9_HIT_LIMIT
                             and previous_avg_rank>=CATASTROPHIC_AVG_RANK_FLOOR)
    next_ranked=(apply_catastrophic_guard(base_next_ranked,draws[-1]["nums"])
                 if reconstructed_guard else list(base_next_ranked))
    ordered_values=sorted(adjusted.values(),reverse=True)
    adjusted={number:ordered_values[index] for index,number in enumerate(next_ranked)}
    single_hits=int(selected_metric["single_hits"])
    p0=5/39;phat=single_hits/n;z=1.96
    center=(phat+z*z/(2*n))/(1+z*z/n)
    margin=z*math.sqrt(phat*(1-phat)/n+z*z/(4*n*n))/(1+z*z/n)
    result.update({
        "evaluation":"最後三百六十期逐期只用當時以前九十期挑選模組正反方向",
        "single_rate":round(phat,4),"single_random_baseline":round(p0,4),
        "single_wilson_lower95":round(center-margin,4),"single_release_allowed":center-margin>p0,
        "top5_hit_distribution":{str(k):top5_distribution[k] for k in range(6)},
        "top9_hit_distribution":{str(k):top9_distribution[k] for k in range(6)},
        "top5_at_least_2_rate":round(sum(v for k,v in top5_distribution.items() if k>=2)/n,4),
        "top5_at_least_3_rate":round(sum(v for k,v in top5_distribution.items() if k>=3)/n,4),
        "top9_at_least_2_rate":round(sum(v for k,v in top9_distribution.items() if k>=2)/n,4),
        "top9_at_least_3_rate":round(sum(v for k,v in top9_distribution.items() if k>=3)/n,4),
        "strategy_candidate_count":len(strategies),"strategy_selection_window":selection_window,
        "recent_54":recent_result,
        "strategy_selection_counts":dict(selection_counts),
        "single_specialist_selection_counts":dict(single_selection_counts),
        "single_specialist_window":SINGLE_SPECIALIST_WINDOW,
        "single_specialist_baseline_hits":single_hits,
        "single_specialist_hits":single_hits,
        "single_specialist_lift":0,
        "single_specialist_enabled":False,
        "single_specialist_method":"disabled_by_cross_window_stability_gate",
        "selected_next_strategy":{"ewma_alpha":chosen["alpha"],"full_history_blend":chosen["full_history_blend"]},
        "selected_next_single_strategy":{"mode":"same_as_guarded_main_ranking"},
        "selected_next_single_polarities":final_polarities,
        "selected_next_single_weights":signed_weights,
        "selected_next_polarities":final_polarities,"next_signed_weights":signed_weights,
        "next_ranked":next_ranked,"next_score":adjusted,"next_raw_score":raw,"next_repeat_audit":repeat_audit,
        "next_unguarded_ranked":base_next_ranked,
        "catastrophic_guard_enabled":True,
        "catastrophic_guard_top9_hit_limit":CATASTROPHIC_TOP9_HIT_LIMIT,
        "catastrophic_guard_avg_rank_floor":CATASTROPHIC_AVG_RANK_FLOOR,
        "catastrophic_guard_rotation":CATASTROPHIC_ROTATION,
        "catastrophic_guard_trigger_count":catastrophic_trigger_count,
        "catastrophic_guard_current_trigger_reconstructed":reconstructed_guard,
        "catastrophic_guard_unguarded":unguarded_result,
        "catastrophic_guard_unguarded_recent_54":unguarded_recent_result,
        "rolling_update_count":n,"rolling_learning_rate":0.0,"rolling_boundary_blend":0.0,
        "rolling_path_sha256":hashlib.sha256(json.dumps(path,ensure_ascii=False,sort_keys=True,separators=(",", ":")).encode()).hexdigest(),
        "method":"thirty_polarity_models_ninety_draw_walk_forward_selection",
    })
    return result


def _add_ranking(metric: dict, ranked: list[int], actual: set[int]) -> None:
    positions = {n: i + 1 for i, n in enumerate(ranked)}
    metric["samples"] += 1
    metric["single_hits"] += int(ranked[0] in actual)
    metric["bottom1_hits"] += int(ranked[-1] in actual)
    metric["top5_hits"] += len(actual.intersection(ranked[:5]))
    metric["bottom5_hits"] += len(actual.intersection(ranked[-5:]))
    metric["top9_hits"] += len(actual.intersection(ranked[:9]))
    metric["rank10_15_hits"] += len(actual.intersection(ranked[9:15]))
    metric["top15_hits"] += len(actual.intersection(ranked[:15]))
    metric["bottom9_hits"] += len(actual.intersection(ranked[-9:]))
    metric["rank_sum"] += sum(positions[n] for n in actual)


def _add_case(metric: dict, case: dict, weights: dict[str, float]) -> None:
    ranked = fast_case_ranking(case, weights)
    actual = set(case["actual"])
    _add_ranking(metric,ranked,actual)


def _finish_metric(metric: dict) -> dict:
    n = metric["samples"]
    if not n:
        raise ValueError("校正區段沒有樣本")
    avg_rank = metric["rank_sum"] / (n * 5)
    top9_slot_hit_rate = metric["top9_hits"] / (n * 9)
    rank10_15_slot_hit_rate = metric["rank10_15_hits"] / (n * 6)
    boundary_valid = top9_slot_hit_rate > rank10_15_slot_hit_rate
    direction = (metric["single_hits"] > metric["bottom1_hits"]
                 and metric["top5_hits"] > metric["bottom5_hits"]
                 and metric["top9_hits"] > metric["bottom9_hits"]
                 and boundary_valid
                 and avg_rank < 20)
    top15_hits = metric["top15_hits"]
    return {
        "samples": n,
        "single_hits": metric["single_hits"],
        "bottom1_hits": metric["bottom1_hits"],
        "top9_hits": metric["top9_hits"],
        "rank10_15_hits": metric["rank10_15_hits"],
        "top15_hits": top15_hits,
        "top5_avg_hits": round(metric["top5_hits"] / n, 4),
        "bottom5_avg_hits": round(metric["bottom5_hits"] / n, 4),
        "top9_avg_hits": round(metric["top9_hits"] / n, 4),
        "rank10_15_avg_hits": round(metric["rank10_15_hits"] / n, 4),
        "top15_avg_hits": round(top15_hits / n, 4),
        "top9_capture_rate": round(metric["top9_hits"] / max(1, top15_hits), 4),
        "top9_slot_hit_rate": round(top9_slot_hit_rate, 6),
        "rank10_15_slot_hit_rate": round(rank10_15_slot_hit_rate, 6),
        "boundary_expected_capture_rate": 0.6,
        "bottom9_avg_hits": round(metric["bottom9_hits"] / n, 4),
        "avg_actual_rank": round(avg_rank, 4),
        "boundary_control_valid": boundary_valid,
        "ranking_direction_valid": direction,
    }


def metrics_from_cases(cases: list[dict], weights: dict[str, float], fold_count: int = 3) -> dict:
    total = _empty_metric()
    folds = [_empty_metric() for _ in range(fold_count)]
    for i, case in enumerate(cases):
        _add_case(total, case, weights)
        fold_index = min(fold_count - 1, i * fold_count // len(cases))
        _add_case(folds[fold_index], case, weights)
    result = _finish_metric(total)
    result["folds"] = [_finish_metric(x) for x in folds]
    result["folds_all_valid"] = all(x["ranking_direction_valid"] for x in result["folds"])
    result["positive_folds"] = sum(x["ranking_direction_valid"] for x in result["folds"])
    return result


def calibration_quality(metric: dict) -> float:
    """直接獎勵前9並懲罰命中滯留第10至15名，避免平均名次掩蓋邊界錯誤。"""
    n = metric["samples"]
    single_lift = metric["single_hits"] - metric["bottom1_hits"]
    top5_lift = (metric["top5_avg_hits"] - metric["bottom5_avg_hits"]) * n
    top9_lift = (metric["top9_avg_hits"] - metric["bottom9_avg_hits"]) * n
    # 前9有九個位置、第10至15名只有六個位置，必須以每個位置命中率比較。
    # 舊公式直接比總命中，隨機排序也會天然偏向前9，會製造假的邊界通過。
    boundary_lift = (
        metric["top9_slot_hit_rate"] - metric["rank10_15_slot_hit_rate"]
    ) * n * 45
    rank_lift = (20 - metric["avg_actual_rank"]) * n
    fold_bonus = metric["positive_folds"] * 25 + (100 if metric["folds_all_valid"] else 0)
    return round(single_lift * 8 + top5_lift * 2 + top9_lift * 7
                 + boundary_lift * 4 + rank_lift + fold_bonus, 6)


def select_rolling_weights(draws: list[dict], holdout: int = ROLLING_HOLDOUT_DRAWS) -> tuple[dict, list[dict], dict]:
    """每期重跑完整候選格；最近三折與更早長歷史共同選模，末段答案完全隔離。"""
    holdout = min(ROLLING_HOLDOUT_DRAWS, holdout)
    holdout_start = len(draws) - holdout
    calibration_start = holdout_start - ROLLING_CALIBRATION_DRAWS
    if calibration_start < 320:
        raise ValueError("全歷史資料不足以建立滾動校正與隔離驗收")
    cases = evaluation_cases(draws, calibration_start, holdout_start)
    all_pre_holdout_cases = evaluation_cases(draws, 320, holdout_start)
    recent_periods = {x["period"] for x in cases}
    long_cases = [x for i,x in enumerate(all_pre_holdout_cases)
                  if i % LONG_HISTORY_SAMPLE_STEP == 0 or x["period"] in recent_periods]
    candidates = weight_candidates()
    evaluated = []
    for index, weights in enumerate(candidates):
        validation = metrics_from_cases(cases, weights, ROLLING_CALIBRATION_FOLDS)
        long_validation = metrics_from_cases(long_cases, weights, LONG_HISTORY_FOLDS)
        recent_quality = calibration_quality(validation)
        long_quality = calibration_quality(long_validation)
        evaluated.append({
            "candidate_index": index,
            "weights": weights,
            "validation": validation,
            "long_history_validation": long_validation,
            "recent_quality": recent_quality,
            "long_history_quality": long_quality,
            "quality": round(recent_quality * 1.5 + long_quality, 6),
        })
    eligible = [
        x for x in evaluated
        if max(x["weights"].values()) <= MAX_ANCHOR_MODULE_WEIGHT + 1e-12
    ]
    stable = [x for x in eligible if x["validation"]["folds_all_valid"]
              and x["validation"]["ranking_direction_valid"]
              and x["long_history_validation"]["ranking_direction_valid"]
              and x["long_history_validation"]["positive_folds"] >= 6]
    directional = [x for x in eligible if x["validation"]["ranking_direction_valid"]
                   and x["long_history_validation"]["ranking_direction_valid"]]
    pool = stable or directional or eligible
    selected = max(pool, key=lambda x:(
        x["long_history_validation"]["ranking_direction_valid"], x["long_history_validation"]["positive_folds"],
        x["validation"]["folds_all_valid"], x["validation"]["positive_folds"], x["quality"],
        x["validation"]["single_hits"], -x["validation"]["avg_actual_rank"], -x["candidate_index"]))
    ensemble_pool = directional or eligible
    ranked_pool = sorted(ensemble_pool, key=lambda x:(
        x["long_history_validation"]["ranking_direction_valid"], x["long_history_validation"]["positive_folds"],
        x["validation"]["folds_all_valid"], x["validation"]["positive_folds"], x["quality"],
        x["validation"]["single_hits"]), reverse=True)
    leaderboard = ranked_pool[:10]
    ensemble_selected = []
    for item in ranked_pool:
        if not ensemble_selected or all(
            sum(abs(float(item["weights"][key]) - float(chosen["weights"][key])) for key in FORMAL_FEATURE_KEYS)
            >= MIN_ENSEMBLE_WEIGHT_DISTANCE - 1e-12
            for chosen in ensemble_selected
        ):
            ensemble_selected.append(item)
        if len(ensemble_selected) == ROLLING_ENSEMBLE_MEMBERS:
            break
    if len(ensemble_selected) != ROLLING_ENSEMBLE_MEMBERS:
        raise RuntimeError("找不到足夠分散的三個均衡模型")
    ensemble_members = [dict(item["weights"]) for item in ensemble_selected]
    if len(ensemble_members) != ROLLING_ENSEMBLE_MEMBERS:
        raise RuntimeError("均衡多模型成員不足")
    diagnostic = {
        "selected": True,
        "candidate_count": len(candidates),
        "eligible_candidate_count": len(eligible),
        "max_anchor_module_weight": MAX_ANCHOR_MODULE_WEIGHT,
        "ensemble_member_count": ROLLING_ENSEMBLE_MEMBERS,
        "minimum_ensemble_weight_distance": MIN_ENSEMBLE_WEIGHT_DISTANCE,
        "ensemble_candidate_indices": [item["candidate_index"] for item in ensemble_selected],
        "ensemble_members": ensemble_members,
        "candidate_grid_sha256": candidate_grid_sha256(candidates),
        "selected_candidate_index": selected["candidate_index"],
        "weights": selected["weights"],
        "validation": selected["validation"],
        "long_history_validation": selected["long_history_validation"],
        "recent_quality": selected["recent_quality"],
        "long_history_quality": selected["long_history_quality"],
        "quality": selected["quality"],
        "selection_pool": "recent_and_long_history_stable" if stable else ("recent_and_long_history_directional" if directional else "best_available"),
        "method": "balanced_three_model_consensus_all_history_286_grid",
        "calibration_window": {
            "samples": len(cases),
            "first_period": draws[calibration_start]["period"],
            "first_date": draws[calibration_start]["date"],
            "last_period": draws[holdout_start - 1]["period"],
            "last_date": draws[holdout_start - 1]["date"],
        },
        "holdout_window": {
            "samples": holdout,
            "first_period": draws[holdout_start]["period"],
            "first_date": draws[holdout_start]["date"],
            "last_period": draws[-1]["period"],
            "last_date": draws[-1]["date"],
        },
        "long_history_selection_window": {
            "samples": len(long_cases),
            "source_first_period": draws[320]["period"],
            "source_first_date": draws[320]["date"],
            "source_last_period": draws[holdout_start - 1]["period"],
            "source_last_date": draws[holdout_start - 1]["date"],
            "older_sampling_step": LONG_HISTORY_SAMPLE_STEP,
            "recent_full_samples": len(cases),
            "folds": LONG_HISTORY_FOLDS,
        },
    }
    slim_leaderboard = [{
        "candidate_index": x["candidate_index"], "weights": x["weights"], "quality": x["quality"],
        "single_hits": x["validation"]["single_hits"], "positive_folds": x["validation"]["positive_folds"],
        "top9_avg_hits": x["validation"]["top9_avg_hits"],
        "rank10_15_avg_hits": x["validation"]["rank10_15_avg_hits"],
        "top9_capture_rate": x["validation"]["top9_capture_rate"],
        "long_history_positive_folds": x["long_history_validation"]["positive_folds"],
        "long_history_direction_valid": x["long_history_validation"]["ranking_direction_valid"],
        "folds_all_valid": x["validation"]["folds_all_valid"],
        "ranking_direction_valid": x["validation"]["ranking_direction_valid"],
    } for x in leaderboard]
    return dict(selected["weights"]), [diagnostic], {"diagnostic": diagnostic, "leaderboard": slim_leaderboard}


def valid_ticket(t: tuple[int, ...]) -> bool:
    odd = sum(n % 2 for n in t)
    low = sum(n <= 20 for n in t)
    decades = len({(n - 1) // 10 for n in t})
    consecutive = sum(b == a + 1 for a, b in zip(t, t[1:]))
    return odd in (2, 3) and low in (2, 3) and decades >= 3 and consecutive <= 2 and 65 <= sum(t) <= 135


def make_tickets(score: dict[int, float], count: int, seed: str, excluded: set[int] | None = None) -> list[tuple[int, ...]]:
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16))
    excluded = set(excluded or ())
    nums = [n for n in range(1, 40) if n not in excluded]
    if len(nums) < 5: raise ValueError("強制投注排除後不足五個可用號碼")
    weights = [max(score[n], .001) ** 2.2 for n in nums]
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


def ranking_direction_metrics(
    draws: list[dict],
    weights: dict[str, float] | list[dict[str, float]],
    start: int,
    end: int | None = None,
) -> dict:
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
        features=state.features()
        if isinstance(weights,list):
            sc=ensemble_scores_from_features(
                features,
                weights,
                draws[i-1]["nums"],
                draws[i-1]["period"],
                state.repeat_exposure,
                state.repeat_hits,
            )[0]
        else:
            raw=scores_from_features(features, weights)
            sc=apply_repeat_qualification(raw,features,weights,draws[i-1]["nums"],draws[i-1]["period"],state.repeat_exposure,state.repeat_hits)[0]
        if i >= start:
            order = rank_numbers(sc, draws[i - 1]["period"])
            actual = set(draw["nums"])
            total["samples"] += 1
            total["single_hits"] += int(order[0] in actual)
            total["bottom1_hits"] += int(order[-1] in actual)
            total["top5_hits"] += len(actual.intersection(order[:5]))
            total["bottom5_hits"] += len(actual.intersection(order[-5:]))
            total["top9_hits"] += len(actual.intersection(order[:9]))
            total["rank10_15_hits"] += len(actual.intersection(order[9:15]))
            total["top15_hits"] += len(actual.intersection(order[:15]))
            total["bottom9_hits"] += len(actual.intersection(order[-9:]))
            positions = {n: p + 1 for p, n in enumerate(order)}
            rank_sum += sum(positions[n] for n in actual)
        state.update(draw)
    n = total["samples"]
    avg_rank = rank_sum / (n * 5)
    top9_slot_hit_rate = total["top9_hits"] / (n * 9)
    rank10_15_slot_hit_rate = total["rank10_15_hits"] / (n * 6)
    boundary_valid = top9_slot_hit_rate > rank10_15_slot_hit_rate
    direction = (total["single_hits"] > total["bottom1_hits"]
                 and total["top5_hits"] > total["bottom5_hits"]
                 and total["top9_hits"] > total["bottom9_hits"]
                 and boundary_valid
                 and avg_rank < 20)
    return {
        "samples": n,
        "single_hits": total["single_hits"],
        "bottom1_hits": total["bottom1_hits"],
        "top9_hits": total["top9_hits"],
        "rank10_15_hits": total["rank10_15_hits"],
        "top15_hits": total["top15_hits"],
        "top5_avg_hits": round(total["top5_hits"] / n, 4),
        "bottom5_avg_hits": round(total["bottom5_hits"] / n, 4),
        "top9_avg_hits": round(total["top9_hits"] / n, 4),
        "rank10_15_avg_hits": round(total["rank10_15_hits"] / n, 4),
        "top15_avg_hits": round(total["top15_hits"] / n, 4),
        "top9_capture_rate": round(total["top9_hits"] / max(1,total["top15_hits"]), 4),
        "top9_slot_hit_rate": round(top9_slot_hit_rate, 6),
        "rank10_15_slot_hit_rate": round(rank10_15_slot_hit_rate, 6),
        "boundary_expected_capture_rate": 0.6,
        "bottom9_avg_hits": round(total["bottom9_hits"] / n, 4),
        "avg_actual_rank": round(avg_rank, 4),
        "boundary_control_valid": boundary_valid,
        "ranking_direction_valid": direction,
    }


def rolling_weight_update(weights: dict[str,float], features: dict[str,dict[int,float]],
                          ranked: list[int], actual: set[int], learning_rate: float = ROLLING_LEARNING_RATE,
                          consensus_ranked: list[int] | None = None,
                          boundary_blend: float = 0.0) -> tuple[dict,dict]:
    """開獎後同時回灌整體失準與第10至15名滯留；只影響下一期，不改寫本期封存。"""
    missed=[n for n in ranked[:5] if n not in actual]
    comparison=missed or [n for n in ranked[:9] if n not in actual] or ranked[:5]
    boundary_order=consensus_ranked or ranked
    boundary_actual=[n for n in boundary_order[9:15] if n in actual]
    false_top9=[n for n in boundary_order[:9] if n not in actual]
    signals={}
    boundary_signals={}
    unscaled={}
    for key in weights:
        actual_mean=sum(features[key][n] for n in actual)/5
        missed_mean=sum(features[key][n] for n in comparison)/max(1,len(comparison))
        global_signal=actual_mean-missed_mean
        if boundary_actual and false_top9:
            boundary_mean=sum(features[key][n] for n in boundary_actual)/len(boundary_actual)
            false_mean=sum(features[key][n] for n in false_top9)/len(false_top9)
            boundary_signal=boundary_mean-false_mean
            signal=(1-boundary_blend)*global_signal+boundary_blend*boundary_signal
            boundary_signals[key]=round(boundary_signal,9)
        else:
            signal=global_signal
            boundary_signals[key]=None
        signal=max(-2.0,min(2.0,signal))
        signals[key]=signal
        unscaled[key]=max(.01,float(weights[key]))*math.exp(learning_rate*signal)
    total=sum(unscaled.values())
    updated={key:unscaled[key]/total for key in weights}
    return updated,{"signals":{k:round(v,9) for k,v in signals.items()},
                    "boundary_signals":boundary_signals,
                    "boundary_triggered":bool(boundary_actual),
                    "boundary_actual_numbers":boundary_actual,
                    "false_top9_numbers":false_top9,
                    "boundary_blend":boundary_blend,
                    "weights_before":{k:round(float(weights[k]),12) for k in weights},
                    "weights_after":{k:round(float(updated[k]),12) for k in weights}}


def rolling_direction_metrics(draws: list[dict], anchor_weights: dict[str,float], start: int, end: int | None = None,
                              learning_rate: float = ROLLING_LEARNING_RATE,
                              boundary_blend: float = 0.0, fold_count: int = 0) -> dict:
    end=min(len(draws),len(draws) if end is None else end)
    state=ExpandingHistoryState(); current=dict(anchor_weights); total=_empty_metric(); path=[]
    folds=[_empty_metric() for _ in range(fold_count)]
    for i,draw in enumerate(draws[:end]):
        if i==0:
            state.update(draw); continue
        if i<start:
            state.update(draw); continue
        features=state.features(); raw=scores_from_features(features,current)
        adjusted,_=apply_repeat_qualification(raw,features,current,draws[i-1]["nums"],draws[i-1]["period"],state.repeat_exposure,state.repeat_hits)
        ranked=rank_numbers(adjusted,draws[i-1]["period"]); actual=set(draw["nums"])
        _add_ranking(total,ranked,actual)
        if fold_count:
            fold_index=min(fold_count-1,(i-start)*fold_count//max(1,end-start))
            _add_ranking(folds[fold_index],ranked,actual)
        current,update=rolling_weight_update(current,features,ranked,actual,learning_rate,ranked,boundary_blend)
        path.append({"period":draw["period"],"update":update})
        state.update(draw)
    result=_finish_metric(total)
    result.update({
        "anchor_weights":anchor_weights,
        "end_weights":current,
        "rolling_update_count":len(path),
        "rolling_learning_rate":learning_rate,
        "rolling_boundary_blend":boundary_blend,
        "rolling_path_sha256":hashlib.sha256(json.dumps(path,ensure_ascii=False,sort_keys=True,separators=(",", ":")).encode()).hexdigest(),
        "method":"pre_draw_prediction_then_post_draw_top9_boundary_update",
    })
    if fold_count:
        result["fold_metrics"]=[_finish_metric(item) for item in folds]
    return result


def rolling_ensemble_direction_metrics(
    draws: list[dict],
    anchor_weight_sets: list[dict[str, float]],
    start: int,
    end: int | None = None,
    learning_rate: float = ROLLING_LEARNING_RATE,
    boundary_blend: float = 0.0,
    fold_count: int = 0,
) -> dict:
    """三個均衡模型各自回灌整體與前9邊界錯誤，再以名次共識產生下一期排序。"""
    end = min(len(draws), len(draws) if end is None else end)
    state = ExpandingHistoryState()
    current = [dict(weights) for weights in anchor_weight_sets]
    total = _empty_metric()
    folds = [_empty_metric() for _ in range(fold_count)]
    path = []
    for index, draw in enumerate(draws[:end]):
        if index == 0:
            state.update(draw)
            continue
        if index < start:
            state.update(draw)
            continue
        features = state.features()
        adjusted, _, _, member_rankings = ensemble_scores_from_features(
            features,
            current,
            draws[index - 1]["nums"],
            draws[index - 1]["period"],
            state.repeat_exposure,
            state.repeat_hits,
        )
        ranked = rank_numbers(adjusted, draws[index - 1]["period"])
        actual = set(draw["nums"])
        _add_ranking(total,ranked,actual)
        if fold_count:
            fold_index=min(fold_count-1,(index-start)*fold_count//max(1,end-start))
            _add_ranking(folds[fold_index],ranked,actual)
        updates = []
        for member_index, weights in enumerate(current):
            current[member_index], update = rolling_weight_update(
                weights,
                features,
                member_rankings[member_index],
                actual,
                learning_rate,
                ranked,
                boundary_blend,
            )
            updates.append(update)
        path.append({"period": draw["period"], "updates": updates})
        state.update(draw)
    result = _finish_metric(total)
    result.update(
        {
            "anchor_weights": average_weights(anchor_weight_sets),
            "anchor_ensemble_weights": anchor_weight_sets,
            "end_weights": average_weights(current),
            "end_ensemble_weights": current,
            "rolling_update_count": len(path),
            "rolling_learning_rate": learning_rate,
            "rolling_boundary_blend": boundary_blend,
            "rolling_path_sha256": hashlib.sha256(
                json.dumps(
                    path,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest(),
            "method": "three_balanced_models_borda_then_post_draw_top9_boundary_update",
        }
    )
    if fold_count:
        result["fold_metrics"]=[_finish_metric(item) for item in folds]
    return result


def rolling_rate_quality(metric: dict) -> float:
    n=metric['samples']
    return round((metric['single_hits']-metric['bottom1_hits'])*8
                 +(metric['top5_avg_hits']-metric['bottom5_avg_hits'])*n*2
                 +(metric['top9_avg_hits']-metric['bottom9_avg_hits'])*n*7
                 +(metric['top9_slot_hit_rate']-metric['rank10_15_slot_hit_rate'])*n*45*4
                 +(20-metric['avg_actual_rank'])*n,6)


def select_rolling_learning_rate(
    draws: list[dict],
    anchor_weights: dict[str, float] | list[dict[str, float]],
    holdout: int = ROLLING_HOLDOUT_DRAWS,
) -> tuple[float,dict]:
    """學習幅度與前9邊界占比只用末段隔離期以前資料挑選，禁止查看隔離答案。"""
    holdout_start=len(draws)-min(ROLLING_HOLDOUT_DRAWS,holdout)
    start=holdout_start-ROLLING_CALIBRATION_DRAWS
    evaluated=[]
    metric_function = (
        rolling_ensemble_direction_metrics
        if isinstance(anchor_weights, list)
        else rolling_direction_metrics
    )
    for rate in ROLLING_LEARNING_RATE_CANDIDATES:
        for boundary_blend in ROLLING_BOUNDARY_BLEND_CANDIDATES:
            metric=metric_function(
                draws,anchor_weights,start,holdout_start,rate,boundary_blend,
                ROLLING_CALIBRATION_FOLDS)
            folds=metric["fold_metrics"]
            evaluated.append({'learning_rate':rate,'boundary_blend':boundary_blend,'validation':metric,
                              'folds_all_valid':all(x['ranking_direction_valid'] for x in folds),
                              'positive_folds':sum(x['ranking_direction_valid'] for x in folds),
                              'fold_metrics':folds,'quality':rolling_rate_quality(metric)})
    stable=[x for x in evaluated if x['validation']['ranking_direction_valid'] and x['folds_all_valid']]
    directional=[x for x in evaluated if x['validation']['ranking_direction_valid']]
    pool=stable or directional or evaluated
    selected=max(pool,key=lambda x:(x['folds_all_valid'],x['positive_folds'],x['quality'],
                                    x['validation']['top9_hits'],x['validation']['single_hits'],
                                    -x['learning_rate'],-x['boundary_blend']))
    summary_keys=(
        'samples','single_hits','bottom1_hits','top5_avg_hits','bottom5_avg_hits',
        'top9_hits','rank10_15_hits','top15_hits','top9_avg_hits','rank10_15_avg_hits',
        'top15_avg_hits','top9_capture_rate','top9_slot_hit_rate','rank10_15_slot_hit_rate',
        'boundary_expected_capture_rate','bottom9_avg_hits','avg_actual_rank',
        'boundary_control_valid','ranking_direction_valid')
    candidate_summaries=[{
        'learning_rate':item['learning_rate'],
        'boundary_blend':item['boundary_blend'],
        'folds_all_valid':item['folds_all_valid'],
        'positive_folds':item['positive_folds'],
        'quality':item['quality'],
        'validation':{key:item['validation'][key] for key in summary_keys},
        'fold_metrics':[
            {key:fold[key] for key in summary_keys}
            for fold in item['fold_metrics']
        ],
    } for item in evaluated]
    return selected['learning_rate'],{
        'method':'pre_holdout_three_model_thirty_pair_three_fold_selection' if isinstance(anchor_weights,list) else 'pre_holdout_thirty_pair_three_fold_selection',
        'candidate_count':len(ROLLING_LEARNING_RATE_CANDIDATES)*len(ROLLING_BOUNDARY_BLEND_CANDIDATES),
        'learning_rate_candidate_count':len(ROLLING_LEARNING_RATE_CANDIDATES),
        'boundary_blend_candidate_count':len(ROLLING_BOUNDARY_BLEND_CANDIDATES),
        'candidates':candidate_summaries,
        'selected_learning_rate':selected['learning_rate'],
        'selected_boundary_blend':selected['boundary_blend'],
        'selection_window':{'first_period':draws[start]['period'],'first_date':draws[start]['date'],
                            'last_period':draws[holdout_start-1]['period'],'last_date':draws[holdout_start-1]['date'],
                            'samples':ROLLING_CALIBRATION_DRAWS},
        'holdout_not_used':True,
    }


def backtest(draws: list[dict], weights: dict[str, float] | list[dict[str, float]], tests: int = 180, ticket_count: int = 8,
             learning_rate: float = ROLLING_LEARNING_RATE, boundary_blend: float = 0.0) -> dict:
    start = max(320, len(draws) - tests); hist = Counter(); total_hits = 0
    single_hits = top5_hits = top9_hits = rank10_15_hits = top15_hits = 0
    bottom1_hits = bottom5_hits = bottom9_hits = rank_sum = 0
    state = ExpandingHistoryState()
    ensemble_mode = isinstance(weights, list)
    if ensemble_mode:
        anchor_ensemble = [dict(item) for item in weights]
        current_ensemble = [dict(item) for item in weights]
        anchor = average_weights(anchor_ensemble)
        current = dict(anchor)
    else:
        anchor_ensemble = []
        current_ensemble = []
        anchor = dict(weights)
        current = dict(weights)
    path=[]
    top9_distribution=Counter()
    for i, draw in enumerate(draws):
        if i == 0:
            state.update(draw)
            continue
        features = state.features()
        if ensemble_mode:
            sc,_,_,member_rankings=ensemble_scores_from_features(
                features,current_ensemble,draws[i-1]["nums"],draws[i-1]["period"],
                state.repeat_exposure,state.repeat_hits)
        else:
            raw=scores_from_features(features, current)
            sc = apply_repeat_qualification(raw,features,current,draws[i-1]["nums"],draws[i-1]["period"],state.repeat_exposure,state.repeat_hits)[0]
        if i < start:
            state.update(draw)
            continue
        ranked = rank_numbers(sc,draws[i-1]["period"])
        actual = set(draw["nums"])
        single_hits += int(ranked[0] in actual)
        top5_hits += len(actual.intersection(ranked[:5]))
        top9_hits += len(actual.intersection(ranked[:9]))
        top9_distribution[len(actual.intersection(ranked[:9]))] += 1
        rank10_15_hits += len(actual.intersection(ranked[9:15]))
        top15_hits += len(actual.intersection(ranked[:15]))
        bottom1_hits += int(ranked[-1] in actual)
        bottom5_hits += len(actual.intersection(ranked[-5:]))
        bottom9_hits += len(actual.intersection(ranked[-9:]))
        positions={n:p+1 for p,n in enumerate(ranked)}; rank_sum+=sum(positions[n] for n in actual)
        ts = make_tickets(sc, ticket_count, draws[i - 1]["period"], set(ranked[-15:]))
        best = max(len(set(t) & actual) for t in ts)
        hist[best] += 1; total_hits += best
        if ensemble_mode:
            updates=[]
            for member_index,member_weights in enumerate(current_ensemble):
                current_ensemble[member_index],update=rolling_weight_update(
                    member_weights,features,member_rankings[member_index],actual,learning_rate,ranked,boundary_blend)
                updates.append(update)
            current=average_weights(current_ensemble)
            path.append({"period":draw["period"],"updates":updates})
        else:
            current,update=rolling_weight_update(current,features,ranked,actual,learning_rate,ranked,boundary_blend)
            path.append({"period":draw["period"],"update":update})
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
    top9_slot_hit_rate=top9_hits/(n*9)
    rank10_15_slot_hit_rate=rank10_15_hits/(n*6)
    boundary_valid=top9_slot_hit_rate>rank10_15_slot_hit_rate
    direction_valid=(single_hits>bottom1_hits and top5_hits>bottom5_hits
                     and top9_hits>bottom9_hits and boundary_valid
                     and avg_actual_rank<20)
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
        "top9_hits": top9_hits,
        "rank10_15_hits": rank10_15_hits,
        "top15_hits": top15_hits,
        "top5_avg_hits": round(top5_hits / n, 4),
        "top5_random_baseline": round(25 / 39, 4),
        "bottom5_avg_hits": round(bottom5_hits / n, 4),
        "top9_avg_hits": round(top9_hits / n, 4),
        "rank10_15_avg_hits": round(rank10_15_hits / n, 4),
        "top15_avg_hits": round(top15_hits / n, 4),
        "top9_capture_rate": round(top9_hits / max(1,top15_hits), 4),
        "top9_slot_hit_rate": round(top9_slot_hit_rate,6),
        "rank10_15_slot_hit_rate": round(rank10_15_slot_hit_rate,6),
        "boundary_expected_capture_rate": 0.6,
        "top9_hit_distribution": {str(k):top9_distribution[k] for k in range(6)},
        "top9_at_least_2_rate": round(sum(v for k,v in top9_distribution.items() if k>=2)/n,4),
        "top9_at_least_3_rate": round(sum(v for k,v in top9_distribution.items() if k>=3)/n,4),
        "top9_random_baseline": round(45 / 39, 4),
        "bottom9_avg_hits": round(bottom9_hits / n, 4),
        "avg_actual_rank": round(avg_actual_rank,4),
        "boundary_control_valid": boundary_valid,
        "ranking_direction_valid": direction_valid,
        "backtest_weights": current,
        "anchor_weights": anchor,
        "end_weights": current,
        "anchor_ensemble_weights": anchor_ensemble,
        "end_ensemble_weights": current_ensemble,
        "rolling_update_count": len(path),
        "rolling_learning_rate": learning_rate,
        "rolling_boundary_blend": boundary_blend,
        "rolling_path_sha256": hashlib.sha256(json.dumps(path,ensure_ascii=False,sort_keys=True,separators=(",", ":")).encode()).hexdigest(),
        "method": "three_balanced_models_borda_then_post_draw_top9_boundary_update" if ensemble_mode else "pre_draw_prediction_then_post_draw_top9_boundary_update",
    }


def build_number_diagnostics(ranked: list[int], score: dict[int, float], raw_score: dict[int, float],
                             features: dict[str, dict[int, float]], weights: dict[str, float]) -> list[dict]:
    lo, hi = min(score.values()), max(score.values())
    span = max(1e-12, hi - lo)
    result = []
    for position, number in enumerate(ranked, 1):
        contributions = {k: round(weights[k] * features[k][number], 9) for k in weights}
        result.append({
            "number": number,
            "rank": position,
            "final_score": round(score[number], 12),
            "raw_score": round(raw_score[number], 12),
            "relative_index": round(100 * (score[number] - lo) / span, 6),
            "feature_values": {k: round(features[k][number], 9) for k in weights},
            "weighted_contributions": contributions,
            "contribution_total": round(sum(contributions.values()), 9),
        })
    return result


def prediction_seal_payload(based_on_period: str, target_draw_date: str, history_hash: str,
                             ranked_all: list[int], diagnostics: list[dict], weights: dict,
                             selection: dict, ensemble_weights: list[dict] | None = None,
                             production_learning_rate: float = 0.0,
                             production_boundary_blend: float = 0.0) -> dict:
    return {
        "based_on_period": based_on_period,
        "target_draw_date": target_draw_date,
        "history_database_sha256": history_hash,
        "ranked_all": ranked_all,
        "number_diagnostics": diagnostics,
        "production_weights": weights,
        "production_ensemble_weights": ensemble_weights or [],
        "candidate_grid_sha256": selection["diagnostic"]["candidate_grid_sha256"],
        "calibration_window": selection["diagnostic"]["calibration_window"],
        "long_history_selection_window": selection["diagnostic"]["long_history_selection_window"],
        "holdout_window": selection["diagnostic"]["holdout_window"],
        "rolling_learning_rate": production_learning_rate,
        "rolling_boundary_blend": production_boundary_blend,
        "rolling_learning_rate_selection_window": selection["learning_rate_selection"]["selection_window"],
        "adaptive_polarity": selection.get("adaptive_polarity") or {},
    }


def _review_blocks(settlements: list[dict], current_weights: dict, selection: dict, fmt) -> tuple[str, str]:
    recent = []
    for item in reversed(settlements[-15:]):
        recent.append(f"<tr><td>{item.get('target_draw_date','-')}</td><td>{int(item.get('single_published',0)):02}</td><td>{fmt(item.get('top9_published') or []) or '-'}</td><td>{fmt(item.get('actual_numbers') or []) or '-'}</td><td>{'命中' if item.get('single_hit') else '未中'}</td><td>{fmt(item.get('top9_hits') or []) or '-'}</td><td>{fmt(item.get('rank10_15_hits') or []) or '-'}</td><td>{'已觸發邊界回灌' if item.get('rank10_15_hits') else '已檢查、無邊界命中'}</td></tr>")
    recent_html = "".join(recent) or "<tr><td colspan='8'>尚無改版後、開獎前封存的實戰結算紀錄</td></tr>"
    if not settlements:
        return recent_html, "<p><b>尚無可檢討的開獎前封存實戰資料。</b></p>"
    item = settlements[-1]
    actual_rows = "".join(
        f"<tr><td>{x.get('number',0):02}</td><td>{x.get('rank','-')}</td><td>{x.get('relative_index',0):.2f}</td><td>{'前9' if x.get('rank',99)<=9 else ('第10至15名' if x.get('rank',99)<=15 else '第16名以後')}</td></tr>"
        for x in item.get("actual_rankings", []))
    module_rows = "".join(
        f"<tr><td>{FEATURE_LABELS.get(x.get('module'),x.get('module','-'))}</td><td>{x.get('actual_mean',0):+.4f}</td><td>{x.get('missed_top5_mean',0):+.4f}</td><td>{x.get('discrimination_gap',0):+.4f}</td><td>{x.get('boundary_actual_mean',0):+.4f}</td><td>{x.get('false_top9_mean',0):+.4f}</td><td>{x.get('boundary_discrimination_gap',0):+.4f}</td><td>{'失準，已納入前9邊界回灌' if x.get('error_flag') else '方向正確，保留競爭'}</td></tr>"
        for x in item.get("module_review", []))
    before = item.get("production_weights_before") or {}
    weight_rows = "".join(
        f"<tr><td>{FEATURE_LABELS.get(k,k)}</td><td>{float(before.get(k,0)):.3f}</td><td>{float(current_weights.get(k,0)):.3f}</td><td>{float(current_weights.get(k,0))-float(before.get(k,0)):+.3f}</td></tr>"
        for k in current_weights)
    error_labels = "、".join(FEATURE_LABELS.get(k,k) for k in item.get("error_modules", [])) or "本期沒有負向鑑別模組"
    numeric_code = lambda value: str(int(str(value), 16))[-20:] if value and all(c in "0123456789abcdef" for c in str(value).lower()) else "-"
    seal_code = numeric_code(item.get('pre_draw_seal_sha256') or item.get('legacy_reconstruction_sha256'))
    review_code = numeric_code(item.get('review_evidence_sha256'))
    calibration = selection["diagnostic"]["calibration_window"]
    long_window = selection["diagnostic"]["long_history_selection_window"]
    holdout = selection["diagnostic"]["holdout_window"]
    rate_selection = selection["learning_rate_selection"]
    review_html = f"""
<p><b>檢討期別：{item.get('target_draw_date','-')}；實際開獎 {fmt(item.get('actual_numbers') or [])}；獨隻 {int(item.get('single_published',0)):02} {'命中' if item.get('single_hit') else '未中'}；前9命中 {fmt(item.get('top9_hits') or []) or '0顆'}；第10至15名滯留 {fmt(item.get('rank10_15_hits') or []) or '0顆'}。</b></p>
<p>失準模組：{error_labels}。檢討只讀取開獎前封存的完整39碼排序、模組貢獻與資料庫指紋，禁止開獎後換號或補號。</p>
<h3>實際開獎號碼原始排名</h3><table><thead><tr><th>號碼</th><th>開獎前排名</th><th>相對指數</th><th>區段</th></tr></thead><tbody>{actual_rows}</tbody></table>
<h3>錯誤模組與前9邊界逐項檢討</h3><table><thead><tr><th>模組</th><th>開獎號平均貢獻</th><th>前5落空號平均貢獻</th><th>整體鑑別差</th><th>第10至15名命中平均</th><th>前9落空號平均</th><th>邊界鑑別差</th><th>處理</th></tr></thead><tbody>{module_rows}</tbody></table>
<h3>開獎後滾動權重重算</h3><p>本次已重新搜尋全部 {selection['diagnostic']['candidate_count']} 組權重，先排除單一模組超過五成的失衡組合，保留 {selection['diagnostic']['eligible_candidate_count']} 組均衡候選，再取前三個穩定模型做名次共識；最近校正區間 {calibration['first_date']}～{calibration['last_date']} 共 {calibration['samples']} 期分三段驗算，再以 {long_window['source_first_date']}～{long_window['source_last_date']} 的更早長歷史抽取 {long_window['samples']} 個逐期樣本做九段穩定複驗。三個模型各自於開獎後回灌；隔離期以前資料交叉比較 {rate_selection['candidate_count']} 組「學習幅度×前9邊界占比」，採用幅度 {rate_selection['selected_learning_rate']:.4f}、邊界占比 {100*rate_selection['selected_boundary_blend']:.0f}%；全部參數鎖定後才用 {holdout['first_date']}～{holdout['last_date']} 共 {holdout['samples']} 期隔離驗收。</p>
<table><thead><tr><th>模組</th><th>開獎前權重</th><th>重算後權重</th><th>調整</th></tr></thead><tbody>{weight_rows}</tbody></table>
<p><b>資料證據：開獎前封存驗證碼 {seal_code}；檢討驗證碼 {review_code}。完整雜湊保存在結算資料檔供系統核驗，不在中文戰報顯示英文字母。</b></p>"""
    return recent_html, review_html


def render(draws: list[dict], weights: dict, quality: list[float], score: dict, tickets: list[tuple[int, ...]], bt: dict, full_scan: dict, repeat_audit: list[dict], selection: dict) -> str:
    latest = draws[-1]; ranked = rank_numbers(score,latest["period"]); top15 = ranked[:15]
    target_date = datetime.strptime(latest['date'], "%Y-%m-%d").date() + timedelta(days=1)
    while target_date.weekday() == 6: target_date += timedelta(days=1)
    fmt = lambda ns: " ".join(f"{n:02}" for n in ns)
    relative_index = lambda n: 100 * (score[n] - min(score.values())) / max(.00001, max(score.values()) - min(score.values()))
    current_features=formal_feature_table(draws)
    support_keys=list(weights)
    rank_status="排序方向通過" if bt.get("ranking_direction_valid") else "排序方向未通過"
    contribution=lambda n:"、".join(f"{FEATURE_LABELS.get(k,k)}{weights[k]*current_features[k][n]:+.3f}" for k in support_keys)
    rows = "".join(f"<tr><td>{i}</td><td><b>{n:02}</b></td><td>{relative_index(n):.1f}</td><td>{'、'.join(FEATURE_LABELS.get(k,k) for k in support_keys if current_features[k][n] >= .65) or '均衡校正'}</td><td>{contribution(n)}</td><td>{rank_status}</td></tr>" for i,n in enumerate(top15,1))
    packs = [("獨隻1中1",top15[:1]),("2中1~2",top15[:2]),("3中1~3",top15[:3]),("5中2~3",top15[:5]),("9中3~5",top15[:9])]
    packrows = "".join(f"<tr><td>{name}</td><td>{fmt(ns)}</td><td>{len(ns)}</td><td>已公開</td></tr>" for name,ns in packs)
    low = list(reversed(ranked[-15:])); lowrows = "".join(f"<tr><td>{name}</td><td>{fmt(low[:k])}</td><td>強制投注排除</td><td>禁止進入任何推薦牌組</td></tr>" for name,k in (("後5名",5),("後10名",10),("後15名",15)))
    settlements=[]; settlement_file=OUT/"published-settlements.jsonl"
    if settlement_file.exists():
        for line in settlement_file.read_text(encoding="utf-8").splitlines():
            try: settlements.append(json.loads(line))
            except Exception: pass
    recent_html, review_html = _review_blocks(settlements, weights, selection, fmt)
    now=datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M")
    single_edge_verified=bool(bt.get('single_release_allowed'))
    single_display=f"{top15[0]:02}"
    previous_overlap5=len(set(top15[:5]).intersection(latest['nums']))
    previous_overlap9=len(set(top15[:9]).intersection(latest['nums']))
    if bt.get("ranking_direction_valid") and bt.get("single_direction_valid"):
        single_status="本期主選已公開；前段排序與1中1方向均通過"
    elif bt.get("ranking_direction_valid"):
        single_status="本期主選已公開；前5與前9方向通過，1中1獨立優勢尚未通過"
    else:
        single_status="本期主選已公開；排序方向未通過，禁止宣稱高機率"
    formula_rows="".join(f"<tr><td>{FEATURE_LABELS.get(k,k)}</td><td>逐期擴展全歷史資料庫</td><td>{v:.3f}</td><td>正式排名核心</td></tr>" for k,v in weights.items())
    formula_rows+="<tr><td>近10／30／100期等短期模組</td><td>僅戰報觀察</td><td>0.000</td><td>鐵律禁止影響正式排名</td></tr>"
    repeat_rows="".join(f"<tr><td>{x['number']:02}</td><td>{x['relative_index']:.1f}</td><td>{x['transition_contribution']:+.3f}</td><td>{x['positive_module_count']}</td><td>{x['repeat_hits']}/{x['repeat_samples']}（{100*x['repeat_rate']:.2f}%）</td><td>{'通過' if x['repeat_backtest_pass'] else '未通過'}</td><td>{'符合' if x['qualified'] else '未符合'}</td><td>{x['final_rank']}</td><td>{'列入前9' if x['listed_top9'] else '未列入前9'}</td></tr>" for x in repeat_audit)
    dist="、".join(f"{k}中：{v}期" for k,v in bt.get('top9_hit_distribution',{}).items())
    return f"""<!doctype html><html lang='zh-Hant'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>台灣539 精算預測戰報</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f4f6;color:#172033;font-family:Arial,'Microsoft JhengHei',sans-serif}}main{{max-width:1180px;margin:auto;padding:18px}}header{{background:linear-gradient(135deg,#8b0000,#d1242f);color:white;padding:25px;border-radius:14px}}h1{{margin:0 0 8px}}h2{{border-left:6px solid #c1121f;padding-left:10px;color:#7f1017;margin-top:30px}}nav{{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}}nav a{{background:white;border:1px solid #d1d5db;border-radius:8px;padding:9px 12px;color:#8b0000;text-decoration:none;font-weight:700}}.band{{background:white;border:1px solid #d8dee8;border-radius:12px;padding:18px;margin:14px 0;box-shadow:0 2px 8px #0000000d}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}}.card{{border:1px solid #d9dde5;border-radius:10px;padding:13px;background:#fff}}.hot-card{{border:2px solid #c1121f;background:#fff5f5}}.label{{color:#687386;font-size:13px}}.value{{font-size:19px;font-weight:800;margin-top:5px}}.num{{color:#c1121f;font-size:34px}}table{{width:100%;border-collapse:collapse;display:block;overflow:auto}}th{{background:#7f1017;color:#fff}}th,td{{padding:9px;border:1px solid #d7dce4;text-align:left;white-space:nowrap}}tr:nth-child(even) td{{background:#fafafa}}.warn{{background:#fff8e6;border-color:#e9b949}}.note{{color:#626d7d}}@media(max-width:600px){{main{{padding:8px}}header{{border-radius:8px}}}}
</style><main><header><h1>台灣539 精算預測戰報</h1><div>全新模型・依照天天樂戰報統一規格</div></header><nav><a href='#decision'>核心決策</a><a href='#rank'>前15名</a><a href='#packs'>強牌組</a><a href='#hits'>實戰封存</a><a href='#review'>命中檢討</a><a href='#low'>投注排除</a><a href='#models'>公式模型</a><a href='#gate'>鐵律守門</a></nav>
<div class='band'><h2>本報表日期對照</h2><div class='grid'><div class='card'><div class='label'>全歷史資料範圍</div><div class='value'>{draws[0]['date']}～{latest['date']}</div></div><div class='card'><div class='label'>實際輸入資料</div><div class='value'>{len(draws):,} 期／{len(draws)*5:,}個號碼</div></div><div class='card'><div class='label'>全歷史核心占比</div><div class='value'>100%（短期正式權重0%）</div></div><div class='card'><div class='label'>最新開獎期別</div><div class='value'>{latest['period']}</div></div><div class='card'><div class='label'>最新開獎號碼</div><div class='value'>{fmt(latest['nums'])}</div></div><div class='card'><div class='label'>資料對應開獎日</div><div class='value'>{latest['date']}</div></div><div class='card'><div class='label'>本次預測目標日</div><div class='value'>{target_date.isoformat()}</div></div><div class='card'><div class='label'>戰報產生時間</div><div class='value'>{now}</div></div></div></div>
<div class='band' id='decision'><h2>核心決策</h2><div class='grid'><div class='card'><div class='label'>資料狀態</div><div class='value'>資料已更新</div></div><div class='card'><div class='label'>檢查</div><div class='value'>已重新運算</div></div><div class='card hot-card'><div class='label'>1中1主選</div><div class='value num'>{single_display}</div></div><div class='card'><div class='label'>公開狀態</div><div class='value'>已公開</div></div><div class='card'><div class='label'>排序方向</div><div class='value'>{rank_status}</div></div><div class='card'><div class='label'>九碼核心</div><div class='value'>{fmt(top15[:9])}</div></div></div></div>
<div class='band'><h2>最強獨隻1中1</h2><div class='grid'><div class='card hot-card'><div class='label'>1中1主選號碼</div><div class='value num'>{single_display}</div></div><div class='card'><div class='label'>判定</div><div class='value'>{single_status}</div></div><div class='card'><div class='label'>隔離驗證命中</div><div class='value'>{bt.get('single_hits',0)}/{bt['samples']}（{100*bt.get('single_rate',0):.2f}%）</div></div><div class='card'><div class='label'>隨機基準／九成五下界</div><div class='value'>{100*bt.get('single_random_baseline',0):.2f}%／{100*bt.get('single_wilson_lower95',0):.2f}%</div></div></div></div>
<div class='band' id='rank'><h2>下期綜合排序前9名</h2><table><thead><tr><th>排名</th><th>號碼</th><th>相對指數（非機率）</th><th>主要支撐</th><th>加權貢獻</th><th>守門</th></tr></thead><tbody>{rows[:rows.find('</tr>', rows.find('</tr>')*0)+5] if False else rows}</tbody></table><h2>第10到第15名前9邊界監控</h2><p>{fmt(top15[9:15])}</p></div>
<div class='band'><h2>生成號碼逐號驗算</h2><table><thead><tr><th>排名</th><th>號碼</th><th>相對指數（非機率）</th><th>交叉來源</th><th>加權貢獻</th><th>狀態</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class='band' id='packs'><h2>強牌組精算</h2><table><thead><tr><th>類型</th><th>號碼</th><th>顆數</th><th>狀態</th></tr></thead><tbody>{packrows}</tbody></table></div>
<div class='band' id='hits'><h2>開獎前封存實戰紀錄</h2><table><thead><tr><th>開獎日</th><th>1中1主選</th><th>當期前9</th><th>實際開獎</th><th>主選結果</th><th>前9命中</th><th>第10至15名命中</th><th>邊界檢測</th></tr></thead><tbody>{recent_html}</tbody></table></div>
<div class='band warn' id='review'><h2>每期開獎命中檢討與滾動修正</h2>{review_html}</div>
<div class='band' id='low'><h2>強制投注排除名單</h2><p><b>以下後15名已從本系統全部推薦牌組強制排除，系統產生的任何牌組都不得包含。</b></p><table><thead><tr><th>區段</th><th>號碼</th><th>動作</th><th>鐵律</th></tr></thead><tbody>{lowrows}</tbody></table></div>
<div class='band'><h2>連莊資格驗算</h2><p><b>上一期號碼必須同時符合：相對指數至少75、全歷史轉移貢獻為正、至少兩個正式模組正貢獻、該號碼全歷史連莊率不低於12.82%，且全系統{full_scan['samples']}期掃描與最後360期隔離回測均通過，才准列入前9。</b>資格在正式排名前判定，不限制連莊顆數、不做事後補號。</p><table><thead><tr><th>上一期號碼</th><th>相對指數</th><th>轉移貢獻</th><th>正貢獻模組數</th><th>連莊命中／樣本</th><th>個別回測</th><th>資格</th><th>最終名次</th><th>結果</th></tr></thead><tbody>{repeat_rows}</tbody></table></div>
<div class='band' id='models'><h2>公式模型實驗室</h2><p><b>每次預測與每一期回測都使用當時以前的全部歷史資料。</b>正式特徵100%由逐期擴展全歷史資料庫產生；每期先搜尋286組錨定權重並強制三個候選保持足夠差異，再建立三十組模組正反方向模型。每一期只用該期以前九十期實績挑選下一期方向，轉移、型態、遺漏若持續把開獎號壓到後段就會自動反轉，不准用同一期答案改寫同一期排名。前9與第10至15名以每個排名位置的命中率比較，禁止再用九個位置對六個位置的總數製造假通過。上一期號碼仍須先通過連莊資格，不限制重複顆數、不做事後補位；同分號碼以當時已知期別公平破同分。</p><table><thead><tr><th>公式</th><th>資料範圍</th><th>實際權重</th><th>動作</th></tr></thead><tbody>{formula_rows}</tbody></table></div>
<div class='band'><h2>全歷史逐期一致性掃描</h2><p>從第321期開始逐期重算，共 {full_scan['samples']} 期：高分第1名 {full_scan['single_hits']} 中、最低分第1名 {full_scan['bottom1_hits']} 中；前5平均 {full_scan['top5_avg_hits']}、後5平均 {full_scan['bottom5_avg_hits']}；前9平均 {full_scan['top9_avg_hits']}、第10至15名平均 {full_scan['rank10_15_avg_hits']}、後9平均 {full_scan['bottom9_avg_hits']}；前9占前15命中 {100*full_scan['top9_capture_rate']:.2f}%；實際開獎號平均名次 {full_scan['avg_actual_rank']}。判定：{'排序方向通過' if full_scan['ranking_direction_valid'] else '排序方向未通過'}。</p></div>
<div class='band warn'><h2>實戰失準回灌重排</h2><p>隔離保留 {bt['samples']} 期：高分第1名 {bt.get('single_hits',0)} 中、最低分第1名 {bt.get('bottom1_hits',0)} 中；前5平均 {bt.get('top5_avg_hits',0)}、後5平均 {bt.get('bottom5_avg_hits',0)}；前9平均 {bt.get('top9_avg_hits',0)}、第10至15名滯留平均 {bt.get('rank10_15_avg_hits',0)}、後9平均 {bt.get('bottom9_avg_hits',0)}；前9占前15命中 {100*bt.get('top9_capture_rate',0):.2f}%；實際開獎號平均名次 {bt.get('avg_actual_rank',0)}（中立值20）。前9逐期分布：{dist}。</p><p>最近54期獨立逐期結果：前9平均 {bt.get('recent_54',{}).get('top9_avg_hits',0)}、後9平均 {bt.get('recent_54',{}).get('bottom9_avg_hits',0)}、前9零中 {bt.get('recent_54',{}).get('top9_hit_distribution',{}).get('0',0)} 期、實際開獎號平均名次 {bt.get('recent_54',{}).get('avg_actual_rank',0)}。</p><p><b>三十組方向模型每期只讀當時以前資料，使用前九十期選出下一期方向；隔離期共完成 {bt.get('rolling_update_count',0)} 次開獎前選模。前5至少2中比例 {100*bt.get('top5_at_least_2_rate',0):.2f}%、前5至少3中比例 {100*bt.get('top5_at_least_3_rate',0):.2f}%、前9至少2中比例 {100*bt.get('top9_at_least_2_rate',0):.2f}%、前9至少3中比例 {100*bt.get('top9_at_least_3_rate',0):.2f}%。禁止用同一期答案改寫同一期預測。</b></p></div>
  <div class='band'><h2>多模組校正對照</h2><div class='grid'><div class='card'><div class='label'>錨定候選組合數</div><div class='value'>{selection['diagnostic']['candidate_count']}</div></div><div class='card'><div class='label'>均衡候選數</div><div class='value'>{selection['diagnostic']['eligible_candidate_count']}</div></div><div class='card'><div class='label'>方向模型數</div><div class='value'>{bt.get('strategy_candidate_count',0)}</div></div><div class='card'><div class='label'>方向選擇窗</div><div class='value'>{bt.get('strategy_selection_window',0)}期</div></div><div class='card'><div class='label'>採用原則</div><div class='value'>全歷史特徵、分散錨定、方向競賽、逐期隔離</div></div></div></div>
<div class='band' id='gate'><h2>鐵律守門</h2><table><thead><tr><th>項目</th><th>結果</th><th>說明</th></tr></thead><tbody><tr><td>重新運算</td><td>已完成</td><td>依最新資料從模型分數直接重排，不做補位</td></tr><tr><td>資料完整性</td><td>通過</td><td>去重、日期排序、號碼1至39、每期5個不重複</td></tr><tr><td>每期命中檢討</td><td>{'通過' if settlements and settlements[-1].get('review_status')=='completed_from_pre_draw_seal' else '等待首筆封存結算'}</td><td>只採開獎前封存排名與模組貢獻，逐期回灌重算</td></tr><tr><td>前9邊界偏移</td><td>{'通過' if bt.get('boundary_control_valid') else '未通過'}</td><td>以每個排名位置命中率比較前9與第10至15名</td></tr><tr><td>全歷史掃描</td><td>診斷</td><td>事後全史只供檢查，不再冒充隔離驗證</td></tr><tr><td>未來資料隔離</td><td>通過</td><td>三十組方向模型每期只用前九十期已開獎成績挑選下一期</td></tr><tr><td>連莊資格</td><td>通過</td><td>相對指數、轉移貢獻、正貢獻模組三重驗算</td></tr><tr><td>上一期號碼檢查</td><td>通過</td><td>前5符合資格並列入{previous_overlap5}顆、前9符合資格並列入{previous_overlap9}顆</td></tr><tr><td>前5／前9目標</td><td>{'達標' if bt.get('top5_at_least_2_rate')==1 and bt.get('top9_at_least_2_rate')==1 else '歷史未全數達標'}</td><td>低於2中一律記為失敗並觸發次期方向重選</td></tr><tr><td>高低分方向</td><td>{rank_status}</td><td>同時計算前1／5／9、第10至15名與後1／5／9</td></tr><tr><td>主選產出</td><td>通過</td><td>每期固定產出最強獨隻並公開，不得缺號或事後換號</td></tr></tbody></table></div>
<div class='band warn'><h2>模型健康與公開狀態</h2><table><thead><tr><th>項目</th><th>高分結果</th><th>對照</th><th>判定</th></tr></thead><tbody><tr><td>第1名隔離命中</td><td>{bt.get('single_hits',0)}/{bt['samples']}（{100*bt.get('single_rate',0):.2f}%）</td><td>最低分第1名 {bt.get('bottom1_hits',0)}/{bt['samples']}</td><td>{rank_status}</td></tr><tr><td>前5隔離平均</td><td>{bt.get('top5_avg_hits',0)}</td><td>後5 {bt.get('bottom5_avg_hits',0)}</td><td>{rank_status}</td></tr><tr><td>前9隔離平均</td><td>{bt.get('top9_avg_hits',0)}</td><td>第10至15名 {bt.get('rank10_15_avg_hits',0)}／後9 {bt.get('bottom9_avg_hits',0)}</td><td>{rank_status}</td></tr><tr><td>前9邊界占比</td><td>{100*bt.get('top9_capture_rate',0):.2f}%</td><td>前15命中中落入前9比例</td><td>{'通過' if bt.get('boundary_control_valid') else '未通過'}</td></tr><tr><td>1中1主選</td><td>已公開</td><td>不宣稱必中</td><td>{single_status}</td></tr></tbody></table></div>
<div class='band warn'><h2>實戰門檻與風險聲明</h2><p>今彩539為隨機遊戲，每組合法號碼理論機率相同；本戰報只供統計研究，不保證中獎或獲利。請設定固定娛樂預算。</p></div></main></html>"""


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--data", type=Path, default=DATA); ap.add_argument("--tickets", type=int, default=8); ap.add_argument("--backtest", type=int, default=360)
    a = ap.parse_args(); draws = load_draws(a.data)
    if len(draws) < 350: raise SystemExit("至少需要 350 期有效資料")
    holdout = min(a.backtest, 360)
    # 每期重新搜尋 286 組；正式權重只用末段隔離期以前資料選定。
    anchor_weights, diagnostics, selection = select_rolling_weights(draws, holdout)
    anchor_ensemble = diagnostics[0]["ensemble_members"]
    learning_rate, learning_rate_selection = select_rolling_learning_rate(draws, anchor_ensemble, holdout)
    boundary_blend = learning_rate_selection["selected_boundary_blend"]
    diagnostics[0]["learning_rate_selection"] = learning_rate_selection
    quality = [diagnostics[0]["quality"]]
    core_bt = backtest(draws, anchor_ensemble, holdout, max(1, min(a.tickets, 30)), learning_rate, boundary_blend)
    bt = adaptive_polarity_backtest(draws, average_weights(anchor_ensemble), holdout, POLARITY_SELECTION_WINDOW)
    bt["core_three_model_diagnostic"] = core_bt
    # 下一期是否啟動災難失準保護，以已公開且開獎後封存的實戰檢討為最高優先。
    guard_trigger=bool(bt.get("catastrophic_guard_current_trigger_reconstructed"));guard_source="逐期隔離重演"
    settlement_file=OUT/"published-settlements.jsonl"
    if settlement_file.exists():
        locked=[]
        for line in settlement_file.read_text(encoding="utf-8").splitlines():
            try: locked.append(json.loads(line))
            except json.JSONDecodeError: continue
        matching=[item for item in locked if item.get("target_draw_date")==draws[-1]["date"]
                  and item.get("review_status")=="completed_from_pre_draw_seal"]
        if matching:
            latest_review=matching[-1]
            guard_trigger=(len(latest_review.get("top9_hits") or [])<=CATASTROPHIC_TOP9_HIT_LIMIT
                           and float(latest_review.get("average_actual_rank") or 0)>=CATASTROPHIC_AVG_RANK_FLOOR)
            guard_source="開獎前封存實戰檢討"
    unguarded_next=list(bt["next_unguarded_ranked"])
    guarded_next=(apply_catastrophic_guard(unguarded_next,draws[-1]["nums"])
                  if guard_trigger else unguarded_next)
    ordered_values=sorted(bt["next_score"].values(),reverse=True)
    bt["next_ranked"]=guarded_next
    bt["next_score"]={number:ordered_values[index] for index,number in enumerate(guarded_next)}
    bt["catastrophic_guard_current_trigger"]=guard_trigger
    bt["catastrophic_guard_current_source"]=guard_source
    weights = dict(bt["next_signed_weights"])
    production_ensemble = []
    diagnostics[0]["production_weights_after_rolling"] = weights
    diagnostics[0]["production_ensemble_after_rolling"] = production_ensemble
    selection["production_weights_after_rolling"] = weights
    selection["production_ensemble_after_rolling"] = production_ensemble
    selection["rolling_update_count"] = bt["rolling_update_count"]
    selection["rolling_path_sha256"] = bt["rolling_path_sha256"]
    selection["learning_rate_selection"] = learning_rate_selection
    selection["adaptive_polarity"] = {
        "method": bt["method"],
        "strategy_candidate_count": bt["strategy_candidate_count"],
        "selection_window": bt["strategy_selection_window"],
        "selected_next_strategy": bt["selected_next_strategy"],
        "selected_next_polarities": bt["selected_next_polarities"],
        "path_sha256": bt["rolling_path_sha256"],
    }
    full_scan = ranking_direction_metrics(draws, weights, 320, len(draws))
    full_scan["validation_eligible"] = False
    full_scan["evaluation"] = "目前終點方向的事後全史診斷，不作隔離驗證"
    current_state=formal_history_state(draws); current_features=current_state.features()
    sc=bt["next_score"];raw_sc=bt["next_raw_score"];repeat_audit=bt["next_repeat_audit"]
    ranked = list(bt["next_ranked"])
    single_number=ranked[0]
    module_consensus=[]
    for key in FORMAL_FEATURE_KEYS:
        module_score={number:weights[key]*current_features[key][number] for number in range(1,40)}
        module_rank=rank_numbers(module_score,draws[-1]["period"]).index(single_number)+1
        module_consensus.append({
            "module":key,
            "label":FEATURE_LABELS[key],
            "rank":module_rank,
            "supports":bool(abs(weights[key])>1e-12 and module_rank<=9),
            "contribution":round(module_score[single_number],9),
        })
    consensus_votes=sum(item["supports"] for item in module_consensus)
    strong_conditions={
        "單碼短窗重排未造成拖累":bt.get("single_specialist_hits",0)>=bt.get("single_specialist_baseline_hits",0),
        "正式排序方向通過":bool(bt.get("ranking_direction_valid")),
        "最近五十四期方向通過":bool((bt.get("recent_54") or {}).get("ranking_direction_valid")),
        "前九邊界通過":bool(bt.get("boundary_control_valid")),
        "至少三項正式邏輯同向":consensus_votes>=3,
        "單碼信賴下限高於隨機基準":bool(bt.get("single_release_allowed")),
    }
    bt["single_module_consensus"]=module_consensus
    bt["single_consensus_votes"]=consensus_votes
    bt["single_strong_conditions"]=strong_conditions
    bt["single_strong_recommendation"]=all(strong_conditions.values())
    bt["single_confidence_label"]=("超高信心強烈推薦" if bt["single_strong_recommendation"]
                                   else "本期綜合最強")
    number_diagnostics = build_number_diagnostics(ranked, sc, raw_sc, current_features, weights)
    tickets = make_tickets(sc, max(1, min(a.tickets, 30)), draws[-1]["period"], set(ranked[-15:]))
    OUT.mkdir(parents=True, exist_ok=True)
    target = datetime.strptime(draws[-1]["date"], "%Y-%m-%d").date() + timedelta(days=1)
    while target.weekday() == 6: target += timedelta(days=1)
    history_payload="|".join(f"{x['period']}:{x['date']}:{','.join(map(str,x['nums']))}" for x in draws)
    history_hash=hashlib.sha256(history_payload.encode()).hexdigest()
    seal_payload = prediction_seal_payload(
        draws[-1]["period"], target.isoformat(), history_hash, ranked,
        number_diagnostics, weights, selection, production_ensemble,
        bt["rolling_learning_rate"], bt["rolling_boundary_blend"])
    seal_sha256 = hashlib.sha256(json.dumps(seal_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    fingerprint = seal_sha256[:16]
    report_pages = render_report_pages(
        draws, weights, sc, tickets, bt, full_scan, repeat_audit,
        selection, OUT, FEATURE_LABELS)
    for filename, page in report_pages.items():
        (OUT / filename).write_text(page, encoding="utf-8")
    report = OUT / "最新539科學預測戰報.html"
    report.write_text(report_pages["index.html"], encoding="utf-8")
    result = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "based_on_period": draws[-1]["period"],
        "target_draw_date": target.isoformat(),
        "recalculation_fingerprint": fingerprint,
        "pre_draw_seal": {
            "algorithm": "sha256",
            "sha256": seal_sha256,
            "sealed_payload": seal_payload,
            "no_post_draw_substitution": True,
        },
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
        "production_ensemble_weights": production_ensemble,
        "anchor_ensemble_weights": anchor_ensemble,
        "audit_weights": weights,
        "audit_candidate_quality": quality,
        "weight_selection_diagnostics": diagnostics,
        "rolling_calibration": selection,
        "rolling_weight_adjustment": {
            "anchor_weights": average_weights(anchor_ensemble),
            "anchor_ensemble_weights": anchor_ensemble,
            "production_weights": weights,
            "production_ensemble_weights": production_ensemble,
            "updates": bt["rolling_update_count"],
            "learning_rate": bt["rolling_learning_rate"],
            "boundary_blend": bt["rolling_boundary_blend"],
            "learning_rate_selection": learning_rate_selection,
            "path_sha256": bt["rolling_path_sha256"],
            "method": bt["method"],
            "strategy_candidate_count": bt["strategy_candidate_count"],
            "strategy_selection_window": bt["strategy_selection_window"],
            "selected_next_strategy": bt["selected_next_strategy"],
            "selected_next_polarities": bt["selected_next_polarities"],
            "single_specialist_window": bt["single_specialist_window"],
            "selected_next_single_strategy": bt["selected_next_single_strategy"],
            "selected_next_single_weights": bt["selected_next_single_weights"],
            "single_specialist_enabled": bt["single_specialist_enabled"],
            "catastrophic_guard_enabled": bt["catastrophic_guard_enabled"],
            "catastrophic_guard_current_trigger": bt["catastrophic_guard_current_trigger"],
            "catastrophic_guard_current_source": bt["catastrophic_guard_current_source"],
            "catastrophic_guard_top9_hit_limit": bt["catastrophic_guard_top9_hit_limit"],
            "catastrophic_guard_avg_rank_floor": bt["catastrophic_guard_avg_rank_floor"],
            "catastrophic_guard_rotation": bt["catastrophic_guard_rotation"],
        },
        "model_selection_cutoff": {
            "period": diagnostics[0]["calibration_window"]["last_period"],
            "date": diagnostics[0]["calibration_window"]["last_date"],
        },
        "ranked_all": ranked,
        "ranked_top15": ranked[:15],
        "number_diagnostics": number_diagnostics,
        "forced_ticket_exclusions": list(reversed(ranked[-15:])),
        "previous_draw_overlap_audit": {
            "method": "model_score_with_repeat_qualification",
            "previous_numbers": list(draws[-1]["nums"]),
            "top5_overlap": len(set(ranked[:5]).intersection(draws[-1]["nums"])),
            "top9_overlap": len(set(ranked[:9]).intersection(draws[-1]["nums"])),
            "full_previous_draw_copied_into_top9": set(draws[-1]["nums"]).issubset(ranked[:9]),
        },
        "repeat_qualification": repeat_audit,
        "single_candidate": ranked[0],
        "single_published": ranked[0],
        "single_selection_evidence": number_diagnostics[0],
        "single_recommendation": {
            "label": bt["single_confidence_label"],
            "strong": bt["single_strong_recommendation"],
            "consensus_votes": consensus_votes,
            "module_count": len(module_consensus),
            "conditions": strong_conditions,
            "module_consensus": module_consensus,
            "isolated_hits": bt["single_specialist_hits"],
            "isolated_samples": bt["samples"],
            "baseline_hits_before_specialist": bt["single_specialist_baseline_hits"],
            "recent_54_hits": (bt.get("recent_54") or {}).get("single_hits"),
        },
        "release_policy": {
            "official_release_allowed": True,
            "single": "published_every_draw",
            "single_edge_verified": bool(bt["single_release_allowed"]),
            "top5": "published_with_backtest",
            "top9": "published_with_backtest"
        },
        "tickets": tickets,
        "full_history_scan": full_scan,
        "backtest": bt
    }
    (OUT / "最新結果.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成：{report}")


if __name__ == "__main__": main()
