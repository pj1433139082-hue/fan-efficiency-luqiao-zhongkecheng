"""只接收已准备的逐台曲线和当前风量；不计算效率、不访问IoT。"""
from copy import deepcopy
from . import core as combination
from .contract import MACHINES, OUTPUTS, EFFICIENCY_COMMIT, SOURCE_HASHES, check_sources, real, flag, boolean, time_value, blank_result, _validate_curves

def prepare_curves_from_points(request):
    """同事已计算的同台同分钟Q/eta_excel有效点→v1.1曲线；不重复计算效率。"""
    check_sources()
    start, end = time_value(request["history_start"]), time_value(request["history_end"])
    if start >= end:
        raise ValueError("Invalid historical window")
    F = real(request["cleaning_gap_pct"], "cleaning_gap_pct")
    points = request["efficiency_points"]
    if not isinstance(points, list):
        raise ValueError("efficiency_points must be a list")
    grouped = {p: [] for p in MACHINES}
    seen = set()
    rejected = {p: 0 for p in MACHINES}
    for row in points:
        point = row["point_id"]
        if point not in MACHINES:
            raise ValueError("Wrong phase/device")
        stamp = time_value(row["observed_at"])
        if not start <= stamp < end or (point, stamp) in seen:
            raise ValueError("Out-of-window or duplicate device/time")
        seen.add((point, stamp))
        if row["quality"] != "VALID":
            rejected[point] += 1
            continue
        flow = real(row["flow_m3min"], "flow_m3min")
        eta = real(row["eta_excel"], "eta_excel")
        if flow < 0 or not .2 <= eta <= 1:
            raise ValueError("VALID efficiency point has invalid flow or fraction efficiency")
        grouped[point].append((flow, eta * 100))
    curves, audit, summary = {}, [], {}
    for point in MACHINES:
        curve = combination.clean(grouped[point], 20, 100, F)
        curves[point] = curve
        summary[point] = {"valid_points": len(grouped[point]), "upstream_rejected": rejected[point], "n_kept": curve["n_kept"]}
        audit.append({"point_id": point, **summary[point]})
    return {"schema_version": 1, "model_id": "luqiao-phase2-fan-combination", "history_start": start.isoformat(),
        "history_end_exclusive": end.isoformat(), "flow_unit": "m3/min", "efficiency_caliber": "eta_excel",
        "cleaning_gap_pct": F, "source_hashes": dict(SOURCE_HASHES), "efficiency_commit": EFFICIENCY_COMMIT,
        "machines": curves, "quality_summary": summary, "range_basis": "各台已有效历史点经v1.1清洗，非厂家安全边界"}, audit

def recommend(bundle, current, tolerance_pct=5.0):
    """两台共同瞬时风量相加为目标；资格由上游显式提供，在线不计算效率。"""
    check_sources()
    end = _validate_curves(bundle)
    tolerance = real(tolerance_pct, "tolerance_pct")
    if tolerance != 5.0:
        raise ValueError("本版路桥二期已确认的目标容差为5%，改动须另建版本")
    if not isinstance(current, list) or len(current) != 2:
        raise ValueError("current必须包含二期5#、6#各一条同刻快照")
    indexed = {}
    for row in current:
        point = row["point_id"]
        if point not in MACHINES or point in indexed:
            raise ValueError("当前设备错配或重复")
        indexed[point] = row
    if set(indexed) != set(MACHINES):
        raise ValueError("当前二期设备缺失")
    times = {time_value(row["observed_at"]) for row in indexed.values()}
    if len(times) != 1:
        raise ValueError("当前两台风量必须严格同刻，禁止最近值拼接")
    stamp = times.pop()
    if stamp < end:
        raise ValueError("当前时刻早于曲线历史终点，存在未来数据回灌")
    diagnostic = {"observed_at": stamp.isoformat(), "automatic_dispatch": False,
                  "target_mode": "sum_current_actual_flow", "tolerance_pct": 5.0,
                  "history_end_exclusive": end.isoformat(), "devices": {}}
    target, units = 0.0, []
    for point in MACHINES:
        row = indexed[point]
        good = boolean(row["raw_quality_ok"], "raw_quality_ok")
        eligible = boolean(row["eligible"], "eligible")
        if not good or row.get("inlet_flow") is None or row.get("run_flag") is None:
            diagnostic.update(status="CURRENT_DATA_INVALID", reason="当前风量或运行状态缺测/质量无效")
            return blank_result(), diagnostic
        flow = real(row["inlet_flow"], "current.inlet_flow")
        running = flag(row["run_flag"], "current.run_flag")
        if flow < 0 or (running == 0 and flow > combination.EPS):
            diagnostic.update(status="CURRENT_FLOW_RUN_CONFLICT", reason="负风量或停机正风量矛盾")
            return blank_result(), diagnostic
        # 不能因该台不可推荐就把它已经供出的风量从系统目标扣掉。
        target += flow
        curve = deepcopy(bundle["machines"][point])
        if not eligible:
            curve["status"] = "INELIGIBLE"
        units.append({"id": point, "curve": curve})
        diagnostic["devices"][point] = {"name": MACHINES[point], "eligible": eligible,
                                        "current_flow_m3min": flow, "run_flag": running}
    solved = combination.solve(units, target, tolerance)
    diagnostic.update(solved)
    if solved["recommendation"] is None:
        return blank_result(), diagnostic
    selected = dict(zip(solved["recommendation"]["S"], solved["recommendation"]["q"]))
    flows = [float(selected.get(p, 0.0)) for p in MACHINES]
    total = float(solved["recommendation"]["Q_rec"])
    if (abs(sum(flows) - total) > 1e-6 or not target * .95 - 1e-9 <= total <= target * 1.05 + 1e-9):
        raise ValueError("推荐总量守恒或容差检查失败")
    return dict(zip(OUTPUTS, [1, target, total, *flows])), diagnostic
