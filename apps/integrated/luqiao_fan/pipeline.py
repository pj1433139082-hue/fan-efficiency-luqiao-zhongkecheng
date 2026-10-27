"""逐台历史→仓库唯一效率实现→共用v1.1核心；无另一套效率公式。"""
from collections import Counter, defaultdict
from datetime import timedelta
import hashlib
from pathlib import Path
from fan_combination import core as combination, efficiency_adapter as efficiency
from fan_combination.contract import BJ, MACHINES, OUTPUTS, PHYSICAL, EFFICIENCY_COMMIT, SOURCE_HASHES, check_sources, time_value, real, flag, boolean, blank_result, _minute
from fan_combination.strategy import recommend

def prepare_curves(request):
    """逐台原始行→同事分钟聚合→效率→原v1.1曲线，历史窗及F必须显式提供。

    dt_s由数据提供侧声明该样本代表的有效时长；不会拿下一条的时间差填缺口。
    实际权重同时截在下一样本、分钟末、窗口末，保持311既有聚合衔接口径。
    """
    check_sources()
    start, end = time_value(request["history_start"]), time_value(request["history_end"])
    if start >= end:
        raise ValueError("历史起点必须早于右开终点")
    F = real(request["cleaning_gap_pct"], "cleaning_gap_pct")
    rows = request["samples"]
    if not isinstance(rows, list):
        raise ValueError("samples必须是逐台样本列表")
    grouped = defaultdict(list)
    seen = set()
    for raw in rows:
        point = raw["point_id"]
        if point not in MACHINES:
            raise ValueError("非路桥二期5#/6#设备: " + str(point))
        stamp = time_value(raw["observed_at"])
        if not start <= stamp < end:
            raise ValueError("样本必须位于显式历史窗口[start,end)")
        if (point, stamp) in seen:
            raise ValueError("同台同刻重复样本")
        seen.add((point, stamp))
        # 强制显式海拔，绕开上游38.5/28/5m的默认值冲突。
        row = {name: raw[name] for name in PHYSICAL}
        real(row["elevation"], "elevation")
        for name in PHYSICAL[:-1]:
            value = row[name]
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise ValueError(name + "须为数值或null；原始缺失不补零")
        row["run_flag"] = flag(raw["run_flag"], "run_flag")
        dt = real(raw["dt_s"], "dt_s")
        if dt <= 0:
            raise ValueError("dt_s必须为正；不从缺口推算代表时长")
        row["raw_quality_ok"] = boolean(raw["raw_quality_ok"], "raw_quality_ok")
        row.update(time=stamp, dt_s=dt)
        grouped[point].append(row)

    # 仅使用完整分钟，窗口边缘的残缺分钟不补齐。空分钟仍保留质量标记。
    first = _minute(start) + (timedelta(minutes=1) if start != _minute(start) else timedelta())
    minute_stamps = []
    cursor = first
    while cursor + timedelta(minutes=1) <= end:
        minute_stamps.append(cursor)
        cursor += timedelta(minutes=1)
    audit, curves, quality = [], {}, {}
    for point in MACHINES:
        data = sorted(grouped[point], key=lambda r: r["time"])
        buckets = defaultdict(list)
        for i, row in enumerate(data):
            stamp = row["time"]
            minute = _minute(stamp)
            next_time = data[i + 1]["time"] if i + 1 < len(data) else end
            effective = min(row["dt_s"], (next_time - stamp).total_seconds(),
                            (minute + timedelta(minutes=1) - stamp).total_seconds(),
                            (end - stamp).total_seconds())
            sample = {name: row[name] for name in PHYSICAL}
            sample.update(run_flag=row["run_flag"], dt_s=effective)
            if not row["raw_quality_ok"]:
                # 只影响本行，整行质量不合格不进入加权；不按信号分别拼接。
                sample["inlet_flow"] = None
            buckets[minute].append(sample)
        minutes = []
        for stamp in minute_stamps:
            samples = buckets[stamp]
            aggregated = efficiency.aggregate_minute(samples)
            result = {name: None for name in efficiency.OUTPUT_COLUMNS}
            result["quality"] = aggregated["quality"]
            if aggregated["quality"] == efficiency.VALID:
                result = efficiency.compute_row(*(aggregated[name] for name in PHYSICAL))
            # 诊断与组合风量始终使用同一分钟的聚合风量，绝不配瞬时风量。
            minutes.append({"point_id": point, "observed_at": stamp.isoformat(),
                            **{k: aggregated.get(k) for k in (*PHYSICAL, "run_share", "n_samples", "n_invalid")},
                            "coverage_s": sum(s["dt_s"] for s in samples if
                                efficiency.classify_row(*(s[name] for name in PHYSICAL)) in
                                (efficiency.VALID, efficiency.STOPPED)),
                            **{k: result.get(k) for k in efficiency.OUTPUT_COLUMNS}})
        flags = efficiency.mark_outages([m["quality"] for m in minutes])
        for row, q in zip(minutes, flags):
            row["quality"] = q
        valid = [row for row in minutes if row["quality"] == efficiency.VALID]
        cleaned = combination.clean([(row["inlet_flow"], row["eta_excel"] * 100) for row in valid],
                                    efficiency.ETA_RANGE[0] * 100, efficiency.ETA_RANGE[1] * 100, F)
        kept = set(cleaned["kept_rows"])
        for index, row in enumerate(valid, 1):
            row["curve_row"] = index
            row["kept"] = index in kept
        curves[point] = cleaned
        quality[point] = {"raw_rows": len(data), "minute_quality_counts": dict(Counter(flags)),
                          "full_minutes": len(minutes), "valid_minutes": len(valid),
                          "n_kept": cleaned["n_kept"]}
        audit.extend(minutes)
    bundle = {"schema_version": 1, "model_id": "luqiao-phase2-fan-combination",
              "history_start": start.isoformat(), "history_end_exclusive": end.isoformat(),
              "flow_unit": "m3/min", "efficiency_caliber": "eta_excel",
              "cleaning_gap_pct": F, "source_hashes": dict(SOURCE_HASHES),
              "efficiency_commit": EFFICIENCY_COMMIT,
              "machines": curves, "quality_summary": quality,
              "range_basis": "本台完整分钟经v1.1清洗后的历史区间，非厂家安全边界"}
    return bundle, audit
