#!/usr/bin/env python3
"""全歷史多模型重組實驗：所有路由決策只讀取預測點以前的已知答案。"""
from __future__ import annotations

from collections import Counter

from tw539_ultra import (
    DATA,
    FORMAL_FEATURE_KEYS,
    POLARITY_CONSENSUS_MEMBERS,
    POLARITY_EWMA_ALPHAS,
    POLARITY_FULL_HISTORY_BLENDS,
    POLARITY_WARMUP,
    STABILITY_CHAMPION_ANCHOR,
    _add_ranking,
    _empty_metric,
    _finish_metric,
    _metric_prefix,
    _prefix_metric,
    apply_repeat_qualification,
    blend_data_change_ranking,
    blend_direct_full_ranking,
    consensus_borda_score,
    current_data_change_case,
    data_change_cases,
    data_change_prefix,
    data_change_ranking,
    data_change_weights,
    direct_hit_prefix,
    direct_hit_weights,
    enforce_repeat_qualification_ranking,
    evaluation_cases,
    fast_case_ranking,
    load_draws,
    rank_numbers,
    scores_from_features,
)


def metric(rows):
    value = _empty_metric()
    for ranked, actual in rows:
        _add_ranking(value, ranked, actual)
    return _finish_metric(value)


def utility(ranked, actual, weights):
    positions = {number: index + 1 for index, number in enumerate(ranked)}
    top5 = len(actual.intersection(ranked[:5]))
    top9 = len(actual.intersection(ranked[:9]))
    single = int(ranked[0] in actual)
    rank_sum = sum(positions[number] for number in actual)
    return (weights[0] * single + weights[1] * top5 + weights[2] * top9
            + weights[3] * (100 - rank_sum))


def borda(rankings):
    return rank_numbers(consensus_borda_score(rankings), "全歷史多模型路由")


def main():
    draws = load_draws(DATA)
    case_start = 320
    cases = evaluation_cases(draws, case_start, len(draws))
    direct_matrix, direct_vector = direct_hit_prefix(cases)
    changes = data_change_cases(cases)
    change_matrix, change_vector = data_change_prefix(changes)

    def direction_quality(value):
        n = value["samples"]
        return ((value["top9_avg_hits"] - value["bottom9_avg_hits"]) * n * 7
                + (value["top9_slot_hit_rate"] - value["rank10_15_slot_hit_rate"]) * n * 180
                + (20 - value["avg_actual_rank"]) * n)

    strategies = []
    for alpha in POLARITY_EWMA_ALPHAS:
        for full_blend in POLARITY_FULL_HISTORY_BLENDS:
            cumulative = {key: 0.0 for key in FORMAL_FEATURE_KEYS}
            ewma = {key: 0.0 for key in FORMAL_FEATURE_KEYS}
            rows = []
            for count, case in enumerate(cases):
                polarities = {}
                for key in FORMAL_FEATURE_KEYS:
                    full_mean = cumulative[key] / max(1, count)
                    signal = full_blend * full_mean + (1 - full_blend) * ewma[key]
                    polarities[key] = 1.0 if count < POLARITY_WARMUP or signal >= 0 else -1.0
                signed = {key: STABILITY_CHAMPION_ANCHOR[key] * polarities[key]
                          for key in FORMAL_FEATURE_KEYS}
                scale = sum(abs(value) for value in signed.values()) or 1.0
                signed = {key: value / scale for key, value in signed.items()}
                ranked = fast_case_ranking(case, signed)
                actual = set(case["actual"])
                rows.append((ranked, actual, polarities))
                for key in FORMAL_FEATURE_KEYS:
                    observed = sum(case["features"][key][number] for number in actual) / 5
                    cumulative[key] += observed
                    ewma[key] = alpha * ewma[key] + (1 - alpha) * observed
            strategies.append({"alpha": alpha, "blend": full_blend, "rows": rows,
                               "prefix": _metric_prefix(rows)})

    first = len(cases) - 1800
    records = []
    for offset in range(first, len(cases)):
        window_start = max(0, offset - 360)
        chosen = sorted(
            strategies,
            key=lambda item: (
                direction_quality(_prefix_metric(item["prefix"], window_start, offset)),
                _prefix_metric(item["prefix"], window_start, offset)["single_hits"],
                -item["alpha"], -item["blend"],
            ),
            reverse=True,
        )[:POLARITY_CONSENSUS_MEMBERS]
        signed = {
            key: sum(STABILITY_CHAMPION_ANCHOR[key] * item["rows"][offset][2][key]
                     for item in chosen) / len(chosen)
            for key in FORMAL_FEATURE_KEYS
        }
        scale = sum(abs(value) for value in signed.values()) or 1.0
        signed = {key: value / scale for key, value in signed.items()}
        case = cases[offset]
        baseline = fast_case_ranking(case, signed)
        direct = fast_case_ranking(
            case, direct_hit_weights(direct_matrix, direct_vector, offset))
        change = data_change_ranking(
            changes[offset], data_change_weights(change_matrix, change_vector, offset))
        raw = scores_from_features(case["features"], signed)
        _, audits = apply_repeat_qualification(
            raw, case["features"], signed, case["previous_numbers"], case["seed"],
            case["repeat_exposure"], case["repeat_hits"])
        candidates = {"方向共識": baseline, "直接命中": direct}
        for blend in (.15, .35, .60):
            candidates[f"方向直接{int(blend*100)}"] = blend_direct_full_ranking(
                baseline, direct, case["seed"], blend)
        for base_label, base in (("舊", candidates["方向直接15"]),
                                 ("新", candidates["方向直接35"])):
            for preserve in (0, 1, 3, 5):
                for blend in (.25, .50, .75, 1.0):
                    candidates[f"{base_label}增量{int(blend*100)}保{preserve}"] = blend_data_change_ranking(
                        base, change, case["seed"], blend, preserve)
        candidates["三源共識"] = borda([baseline, direct, change])
        candidates["基準增量共識"] = borda([baseline, change])
        candidates = {
            name: enforce_repeat_qualification_ranking(ranked, audits)[0]
            for name, ranked in candidates.items()
        }
        records.append({"candidates": candidates, "actual": set(case["actual"]),
                        "period": case["period"]})

    names = list(records[0]["candidates"])
    calibrate = range(len(records) - 720, len(records) - 360)
    holdout = range(len(records) - 360, len(records))
    configurations = []
    utility_weights = (
        (6.0, 3.0, 5.0, .04),
        (8.0, 4.0, 7.0, .02),
        (10.0, 5.0, 8.0, 0.0),
        (4.0, 2.0, 8.0, .02),
    )
    utility_prefixes = {}
    for weights in utility_weights:
        by_name = {}
        for name in names:
            prefix = [0.0]
            for record in records:
                prefix.append(prefix[-1] + utility(
                    record["candidates"][name], record["actual"], weights))
            by_name[name] = prefix
        utility_prefixes[weights] = by_name
    for window in (30, 54, 90, 120, 180, 240, 360):
        for members in (1, 3, 5, 7):
            for weights in utility_weights:
                rows = []
                for index in calibrate:
                    start = max(0, index - window)
                    scored = []
                    for name in names:
                        prefix = utility_prefixes[weights][name]
                        value = prefix[index] - prefix[start]
                        scored.append((value, name))
                    selected = [name for _, name in sorted(scored, reverse=True)[:members]]
                    ranked = borda([records[index]["candidates"][name] for name in selected])
                    rows.append((ranked, records[index]["actual"]))
                result = metric(rows)
                score = (result["top9_avg_hits"] * 10 + result["top5_avg_hits"] * 5
                         + result["single_hits"] / result["samples"] * 8
                         - abs(result["avg_actual_rank"] - 19.5))
                configurations.append((score, window, members, weights, result))
    configurations.sort(reverse=True, key=lambda item: item[0])
    _, window, members, weights, calibration = configurations[0]
    routed = []
    choices = Counter()
    for index in holdout:
        start = max(0, index - window)
        scored = []
        for name in names:
            prefix = utility_prefixes[weights][name]
            value = prefix[index] - prefix[start]
            scored.append((value, name))
        selected = [name for _, name in sorted(scored, reverse=True)[:members]]
        choices.update(selected)
        ranked = borda([records[index]["candidates"][name] for name in selected])
        routed.append((ranked, records[index]["actual"]))

    static = []
    for name in names:
        rows = [(records[index]["candidates"][name], records[index]["actual"]) for index in holdout]
        blocks=[]
        for block_start in range(0,len(records),360):
            block=[(records[index]["candidates"][name],records[index]["actual"])
                   for index in range(block_start,block_start+360)]
            blocks.append(metric(block))
        static.append((metric(rows)["top9_avg_hits"], name, metric(rows), metric(rows[-54:]), metric(rows[-120:]), blocks))
    static.sort(reverse=True, key=lambda item: item[0])
    recent54 = sorted(static, reverse=True, key=lambda item: item[3]["top9_avg_hits"])
    recent120 = sorted(static, reverse=True, key=lambda item: item[4]["top9_avg_hits"])
    def compact(items):
        return [{"name": item[1],
                 "h360": (item[2]["single_hits"], item[2]["top5_avg_hits"], item[2]["top9_avg_hits"]),
                 "h54": (item[3]["single_hits"], item[3]["top5_avg_hits"], item[3]["top9_avg_hits"]),
                 "h120": (item[4]["single_hits"], item[4]["top5_avg_hits"], item[4]["top9_avg_hits"]),
                 "blocks": [(block["single_hits"],block["top5_avg_hits"],block["top9_avg_hits"])
                            for block in item[5]]}
                for item in items]
    print({"selected": {"window": window, "members": members, "weights": weights,
                         "calibration": calibration},
           "holdout": metric(routed), "recent54": metric(routed[-54:]),
           "recent120": metric(routed[-120:]), "choices": choices.most_common(),
           "best_static_holdout": compact(static[:8]),
           "best_recent54": compact(recent54[:8]),
           "best_recent120": compact(recent120[:8])})


if __name__ == "__main__":
    main()
