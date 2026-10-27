"""风机组合公共算法：按用户确认整合 v1.1 的 C33:C41。

两厂调用同一个算法，避免各维护一份而逐渐产生规则差异。
输入是逐台实测曲线，输出仅为建议；历史风量上下限不是厂家喘振/安全边界。
delivery/v1.2 保留原始模拟回归；本文件不包含效率计算公式。
"""
from __future__ import annotations

import itertools
import math

EPS = 1e-9  # 仅处理浮点舍入误差；业务风量容差仍是 5%，二者不要混淆。


def number(value):
    """只接受有限数值，拒绝 NaN/无穷和把布尔值当作风量/效率的情况。"""
    if isinstance(value, bool):
        raise ValueError("boolean is not a measurement")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("non-finite measurement")
    return result


def _gap(left, right, side):
    """低端分母取右点，高端取左点；分母为 0 的真实跳跃按无限偏离处理。"""
    denominator = abs(right if side == "low" else left)
    delta = abs(right - left)
    return delta / denominator * 100 if denominator else (math.inf if delta else 0.0)


def _clusters(points, threshold, dimension):
    """从两端分别向内找首个 >F 的间隔；间隔外的全部点构成候选异常簇。"""
    choices = []
    # 与新版工具一致：每侧扫描不越过会只留下一个点的最末间隔。
    for i in range(len(points) - 2):
        gap = _gap(points[i][dimension], points[i + 1][dimension], "low")
        if gap > threshold:
            choices.append((i + 1, -gap, 0, "low", gap))
            break
    for i in range(len(points) - 2, 0, -1):
        gap = _gap(points[i][dimension], points[i + 1][dimension], "high")
        if gap > threshold:
            choices.append((len(points) - i - 1, -gap, 1, "high", gap))
            break
    return choices


def clean(points, D, E, F, *, flow_min=None, flow_max=None):
    """逐台清洗，返回区间、平均效率及剔除明细。

    D/E：效率百分数上下限，闭区间筛选；填反按原规则交换。
    flow_min/max：与输入风量同单位的筛选范围，填反交换；低层调用可省略。
    F：风量与效率两维共用的相对偏离度（%）；F≤0 不进行异常簇剔除。
    扫描不是每次只删一个点：必须整簇比较、整簇剔除、重新扫描。
    新版少于三点停止剔除，只要还剩点即可用；点数始终保留供调用方复核。
    """
    D, E, F = number(D), number(E), number(F)
    D, E = sorted((D, E))  # 原 v1.0 参数规则：效率上下限填反自动交换。
    if not 0 <= D <= E <= 100:
        raise ValueError("efficiency bounds must be percentages in [0,100]")
    if (flow_min is None) != (flow_max is None):
        raise ValueError("flow bounds must be provided together")
    if flow_min is not None:
        flow_min, flow_max = sorted((number(flow_min), number(flow_max)))
        if flow_min < 0:
            raise ValueError("negative flow bound")
    kept, invalid, rejected_eff, rejected_dev, rejected_range = [], [], [], [], []
    for index, point in enumerate(points, 1):
        try:
            q, e = map(number, point)
            if q < 0:
                raise ValueError("negative flow")
        except (TypeError, ValueError, OverflowError):
            invalid.append(index)
            continue
        reasons = []
        if flow_min is not None and not flow_min <= q <= flow_max:
            reasons.append("flow")
        if not D <= e <= E:
            reasons.append("efficiency")
            rejected_eff.append((q, e))
        if reasons:
            rejected_range.append({"row": index, "point": (q, e), "dimensions": reasons})
        else:
            kept.append((q, e, index))
    # 先风量、后效率；每维独立循环，效率清洗结束后不重新启动风量清洗。
    for dimension, name in ((0, "flow"), (1, "efficiency")):
        kept.sort(key=lambda p: p[dimension])
        while len(kept) >= 3 and F > 0:
            choices = _clusters(kept, F, dimension)
            if not choices:
                break
            count, _, _, side, gap = min(choices)
            removed = kept[:count] if side == "low" else kept[-count:]
            rejected_dev.append({"dimension": name, "side": side,
                                 "points": [(q, e) for q, e, _ in removed],
                                 "rows": [row for _, _, row in removed],
                                 "gap_pct": gap if math.isfinite(gap) else "INF"})
            kept = kept[count:] if side == "low" else kept[:-count]
    kept.sort(key=lambda p: p[0])
    return {
        "status": "OK" if kept else "INSUFFICIENT_POINTS", "rule_version": "1.1",
        "qs": [q for q, _, _ in kept], "es": [e for _, e, _ in kept],
        "q_min": kept[0][0] if kept else None,
        "q_max": kept[-1][0] if kept else None,
        # 原规则用保留点算术平均；内部用小数效率，非实时单工况效率。
        "eta": sum(e for _, e, _ in kept) / len(kept) / 100 if kept else None,
        "n_kept": len(kept), "need_review": False, "sample_count_lt3": 0 < len(kept) < 3,
        "kept_rows": [row for _, _, row in kept], "rejected_range": rejected_range,
        "invalid_rows": invalid, "rejected_eff": rejected_eff,
        "rejected_dev": rejected_dev, "D": D, "E": E, "F": F,
        "configured_flow_min": flow_min, "configured_flow_max": flow_max,
    }


def validate_parameters(parameters):
    """在尚无历史/效率时也校验显式参数，避免 NaN 绕过过滤或空曲线掩盖坏配置。"""
    lo, hi = sorted((number(parameters["flow_min"]), number(parameters["flow_max"])))
    if lo < 0:
        raise ValueError("negative flow bound")
    E, F = number(parameters["E"]), number(parameters["F"])
    if not 0 <= E <= 100:
        raise ValueError("efficiency upper bound must be in [0,100]")
    if (parameters.get("D") is None) == (parameters.get("margin_pct") is None):
        raise ValueError("supply exactly one of D or margin_pct")
    if parameters.get("D") is not None:
        if not 0 <= number(parameters["D"]) <= 100:
            raise ValueError("efficiency lower bound must be in [0,100]")
    elif number(parameters["margin_pct"]) < 0:
        raise ValueError("negative efficiency margin")
    return lo, hi, E, F


def clean_configured(points, parameters, flow_factor=1.0):
    """厂站/直接曲线入口共用参数适配，保留旧 D/E 的效率字段含义。

    新版表 D 的风量范围映射为 flow_min/flow_max，单位与该曲线原始风量一致。
    points 已归一至 m³/min；只把参数上下限乘相同换算系数，不重复换算散点。
    裕量推导只用风量范围内的实际点，避免范围外峰值抬高效率下限。
    """
    factor = number(flow_factor)
    if factor <= 0:
        raise ValueError("invalid flow conversion factor")
    lo, hi, E, F = validate_parameters(parameters)
    lo, hi = lo * factor, hi * factor
    in_range = [p for p in points if lo <= p[0] <= hi]
    # 范围内没有点时给空曲线审计，不能从范围外借一个效率峰值。
    D = (number(parameters["D"]) if parameters.get("D") is not None else
         derive_lower(in_range, E, parameters["margin_pct"]) if in_range else 0.0)
    result = clean(points, D, E, F, flow_min=lo, flow_max=hi)
    result["D_derived"] = parameters.get("D") is None
    if result["D_derived"] and not in_range:
        result["D"] = None  # 内部空曲线过滤不代表已推导或确认 D=0。
    return result


def derive_lower(points, upper_pct, margin_pct):
    """按 v1.2 §2.2 的“实测最高效率－显式裕量”推导 D，不四舍五入。

    例如输入裕量 8，含义是减 8 个百分点，绝不是乘 92%。
    本函数只推 D；E、采样密度阈值 F、现场安全边界仍需各自的实际依据。
    """
    upper, margin = number(upper_pct), number(margin_pct)
    if not 0 < upper <= 100 or margin < 0:
        raise ValueError("invalid upper efficiency or margin")
    valid = []
    for point in points:
        try:
            q, e = map(number, point)
            if q >= 0 and 0 < e <= upper:
                valid.append(e)
        except (TypeError, ValueError, OverflowError):
            continue
    if not valid:
        raise ValueError("no valid measured efficiency")
    lower = max(valid) - margin
    if lower < 0:
        raise ValueError("derived D is negative; review the margin")
    return lower


def allocate(units, total):
    """原规则水填充分配，保证每台 lo≤q≤hi 且总量守恒。

    先给每台下限 lo，剩余量按 (hi-lo)×平均效率加权分配。
    超过上限的机台钉在上限、退出权重池，剩余量重新分配。
    此权重不是边际电耗，不能据此宣称全局最低功率。
    """
    total = number(total)
    units = [{k: number(u[k]) for k in ("lo", "hi", "eta")} for u in units]
    for unit in units:
        lo, hi, eta = (unit[k] for k in ("lo", "hi", "eta"))
        if not 0 <= lo <= hi or not 0 <= eta <= 1:
            raise ValueError("invalid allocation unit")
    lower = sum(u["lo"] for u in units)
    upper = sum(u["hi"] for u in units)
    if not units or not lower - EPS <= total <= upper + EPS:
        raise ValueError("total outside allocation bounds")
    remaining = min(max(total - lower, 0.0), upper - lower)
    x = [0.0] * len(units)
    pool = [i for i, u in enumerate(units) if u["hi"] > u["lo"]]
    while pool and remaining > EPS:  # 总量已等于下限或容量为 0 时无需除以权重。
        weights = {i: (units[i]["hi"] - units[i]["lo"]) * units[i]["eta"]
                   for i in pool}
        weight = sum(weights.values())
        if weight <= 0:
            raise ValueError("positive flow has no positive allocation weight")
        proposal = {i: remaining * weights[i] / weight for i in pool}
        over = [i for i in pool if proposal[i] > units[i]["hi"] - units[i]["lo"]]
        if not over:
            for i in pool:
                x[i] = proposal[i]
            break
        for i in over:
            x[i] = units[i]["hi"] - units[i]["lo"]
            remaining -= x[i]
            pool.remove(i)
    result = [u["lo"] + x[i] for i, u in enumerate(units)]
    if (any(not u["lo"] - EPS <= q <= u["hi"] + EPS for u, q in zip(units, result))
            or abs(sum(result) - total) > 1e-6):
        raise ValueError("allocation violates bounds/conservation")
    return result


def solve(units, target, tolerance):
    """逐台枚举，每台 G=1；配置停用的 G=0 由两厂入口事先排除。

    units 中每台都有独立身份和已清洗曲线，禁止复制合并曲线冒充逐台差异。
    可行方案在 candidates，不满足目标的方案单列 reference_candidates。
    无解仍返回空推荐和原因；参考分配不能进入逐台执行建议。
    """
    target, tolerance = number(target), number(tolerance)
    if target < 0 or not 0 <= tolerance <= 100:
        raise ValueError("invalid target/tolerance")
    ids = [u["id"] for u in units]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate unit identity")
    answer = {"status": "NO_FEASIBLE", "reason": "No interval overlaps target band",
              "target": target, "tolerance_pct": tolerance,
              "band": [target * (1 - tolerance / 100), target * (1 + tolerance / 100)],
              "candidates": [], "reference_candidates": [], "recommendation": None,
              "automatic_dispatch": False, "rule_version": "1.1"}
    ready = []
    excluded = []
    for unit in units:
        curve = unit["curve"]
        if curve["status"] != "OK":
            excluded.append({"id": unit["id"], "reason": curve["status"]})
        else:
            ready.append({"id": unit["id"], "lo": curve["q_min"],
                          "hi": curve["q_max"], "eta": curve["eta"]})
    answer["excluded"] = excluded
    if not ready:
        answer.update(status="NO_AVAILABLE_UNITS", reason="No usable cleaned curves")
        return answer
    tl, th = answer["band"]
    for count in range(1, len(ready) + 1):  # 排除全部不开的组合，符合原始规则。
        for group in itertools.combinations(ready, count):
            lo, hi = sum(u["lo"] for u in group), sum(u["hi"] for u in group)
            a, b = max(lo, tl), min(hi, th)
            feasible = a <= b
            # 无交集仅计算区间内最近边界作为参考，不扩大设备能力。
            total = min(max(target, a), b) if feasible else min(max(target, lo), hi)
            try:
                flows = allocate(group, total)
            except ValueError:
                continue
            answer["candidates" if feasible else "reference_candidates"].append({
                "S": [u["id"] for u in group], "n": count, "ok": feasible,
                "Qlo": lo, "Qhi": hi, "dev": max(lo - target, target - hi, 0.0),
                "width": hi - lo, "eta": sum(u["eta"] for u in group) / count,
                "Q_rec": total, "q": flows,
            })
    # 原五级排序：满足→少台数→小偏差→窄区间→高平均效率；首项均为满足。
    for key in ("candidates", "reference_candidates"):
        answer[key].sort(key=lambda c: (not c["ok"], c["n"], c["dev"], c["width"], -c["eta"]))
    if answer["candidates"]:
        answer.update(status="OK", reason=None, recommendation=answer["candidates"][0])
    return answer
